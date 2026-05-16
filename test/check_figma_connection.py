import os
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from shared import config
    from adapters.figma.figma_adapter import FigmaAdapter, _extract_file_key
except ImportError:
    print("[-] Error: Could not import project modules. Run from the project root or the test folder.")
    sys.exit(1)


PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"


def _build_adapter() -> FigmaAdapter | None:
    """Build adapter directly from config — no interactive input()."""
    token = config.FIGMA_ACCESS_TOKEN
    url   = config.FIGMA_FILE_URL

    if not token or token == "your_figma_access_token_here":
        print(f"{FAIL} FIGMA_ACCESS_TOKEN is missing or a placeholder in .env")
        return None

    if not url:
        print(f"{FAIL} FIGMA_URL_QA is missing in .env — add it as:")
        print("       FIGMA_URL_QA=https://www.figma.com/design/<key>/...")
        return None

    file_key = _extract_file_key(url)
    if not file_key or file_key == url.strip():
        print(f"{FAIL} Could not extract file key from FIGMA_URL_QA: {url!r}")
        return None

    print(f"[*] File key: {file_key}")
    return FigmaAdapter(file_key=file_key, access_token=token)




def check_auth() -> bool:
    import requests

    token = config.FIGMA_ACCESS_TOKEN
    if not token or token == "your_figma_access_token_here":
        print(f"{FAIL} FIGMA_ACCESS_TOKEN is missing or not set in .env")
        return False

    url = f"{config.FIGMA_API_BASE}/me"
    print(f"[*] Authenticating at {url} ...")
    try:
        resp = requests.get(url, headers={"X-FIGMA-TOKEN": token}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print(f"{PASS} Auth OK — user: {data.get('handle', '?')} (id: {data.get('id', '?')})")
            return True
        elif resp.status_code in (401, 403):
            print(f"{FAIL} Auth failed ({resp.status_code}): token is expired or invalid.")
        else:
            print(f"{FAIL} Unexpected status {resp.status_code}")
    except Exception as e:
        print(f"{FAIL} Request error: {e}")
    return False



def check_predefined_mode(adapter: FigmaAdapter) -> bool:
    print("\n" + "=" * 55)
    print("[*] PREDEFINED MODE — Figma capability checks")
    print("=" * 55)
    all_passed = True

    print("\n[1] get_all_frames() ...")
    frames = adapter.get_all_frames()
    if frames:
        print(f"{PASS} {len(frames)} frame(s) found.")
    else:
        print(f"{FAIL} No frames returned. Check the file key and token scopes.")
        all_passed = False

    print("\n[2] get_flow_summary() ...")
    summary = adapter.get_flow_summary()
    if summary and "No Figma frames" not in summary:
        preview = summary[:200].replace("\n", " ")
        print(f"{PASS} Summary OK — preview: {preview}...")
    else:
        print(f"{FAIL} Empty or error summary: {summary!r}")
        all_passed = False

    if not frames:
        print(f"{SKIP} Skipping screenshot / context tests — no frames available.")
        return all_passed

    first_id = frames[0]["id"]

    print(f"\n[3] get_node_context({first_id!r}) ...")
    context = adapter.get_node_context(first_id)
    if context:
        name = context.get("document", {}).get("name", "(no name)")
        print(f"{PASS} Context OK — frame name: {name!r}")
    else:
        print(f"{FAIL} Empty context returned for node {first_id!r}")
        all_passed = False

    print(f"\n[4] get_node_screenshot_b64({first_id!r}) ...")
    b64 = adapter.get_node_screenshot_b64(first_id)
    if b64:
        print(f"{PASS} Screenshot OK — base64 length: {len(b64)} chars")
    else:
        print(f"{FAIL} No screenshot returned for node {first_id!r}")
        all_passed = False

    print(f"\n[5] save_composite_gold_standard([{first_id!r}]) ...")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        adapter.save_composite_gold_standard([first_id], tmp_path)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            print(f"{PASS} Composite image written ({os.path.getsize(tmp_path)} bytes)")
        else:
            print(f"{FAIL} Composite image file empty or not created at {tmp_path!r}")
            all_passed = False
    except Exception as e:
        print(f"{FAIL} save_composite_gold_standard raised: {e}")
        all_passed = False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return all_passed




def check_autonomous_mode(adapter: FigmaAdapter) -> bool:
    print("\n" + "=" * 55)
    print("[*] AUTONOMOUS MODE — Figma capability checks")
    print("=" * 55)
    all_passed = True

    print("\n[1] get_all_frames() ...")
    frames = adapter.get_all_frames()
    if frames:
        print(f"{PASS} {len(frames)} frame(s) available for LLM discovery.")
    else:
        print(f"{FAIL} No frames returned. Auto-discovery will fail at runtime.")
        all_passed = False

    if not frames:
        print(f"{SKIP} Skipping trace / screenshot tests — no frames available.")
        return all_passed

    start_id = frames[0]["id"]

    print(f"\n[2] trace_prototype_path({start_id!r}, dummy_steps=[]) ...")
    try:
        path = adapter.trace_prototype_path(start_id, [])
        if path:
            print(f"{PASS} Path resolved: {path}")
        else:
            print(f"{FAIL} Empty path returned.")
            all_passed = False
    except Exception as e:
        print(f"{FAIL} trace_prototype_path raised: {e}")
        all_passed = False

    print(f"\n[3] get_node_screenshot_b64({start_id!r}) ...")
    b64 = adapter.get_node_screenshot_b64(start_id)
    if b64:
        print(f"{PASS} Screenshot OK — base64 length: {len(b64)} chars")
    else:
        print(f"{FAIL} No screenshot returned.")
        all_passed = False

    print(f"\n[4] save_screenshot_to_file({start_id!r}) ...")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        ok = adapter.save_screenshot_to_file(start_id, tmp_path)
        if ok and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            print(f"{PASS} File saved ({os.path.getsize(tmp_path)} bytes)")
        else:
            print(f"{FAIL} File empty or save returned False.")
            all_passed = False
    except Exception as e:
        print(f"{FAIL} save_screenshot_to_file raised: {e}")
        all_passed = False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return all_passed



if __name__ == "__main__":
    print("=" * 55)
    print("[*] MAS AI — Figma Connection & Capability Checker")
    print("=" * 55)

    if not check_auth():
        print("\n[-] Auth failed. Fix your FIGMA_ACCESS_TOKEN before proceeding.")
        sys.exit(1)

    adapter = _build_adapter()
    if adapter is None:
        print("\n[-] Could not build adapter. Fix the errors above.")
        sys.exit(1)

    pred_ok = check_predefined_mode(adapter)
    auto_ok = check_autonomous_mode(adapter)

    print("\n" + "=" * 55)
    print("[*] SUMMARY")
    print("=" * 55)
    print(f"  Auth:              {PASS}")
    print(f"  Predefined mode:   {PASS if pred_ok else FAIL}")
    print(f"  Autonomous mode:   {PASS if auto_ok else FAIL}")

    if not pred_ok or not auto_ok:
        print("\n[-] One or more checks failed. Review the output above.")
        sys.exit(1)
    else:
        print("\n[+] All checks passed. Both modes are ready to run.")
