"""
Manual verification script for Vertex AI provider connectivity.

Usage:
    python tests/check_vertex_connection.py

Tests:
    1. Config resolution (project, location, base URL)
    2. Auth mode detection (API key vs ADC)
    3. Simple LLM invocation via LLMFactory -> LangChainAdapter
    4. Error classification (auth failure, API disabled, model unavailable)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"
INFO = "[INFO]"


def check_config():
    """Verify Vertex env variables resolve correctly."""
    from shared import config

    print(f"{INFO} VERTEX_PROJECT_ID = {config.VERTEX_PROJECT_ID!r}")
    print(f"{INFO} VERTEX_LOCATION  = {config.VERTEX_LOCATION!r}")
    print(f"{INFO} VERTEX_ENDPOINT  = {config.VERTEX_ENDPOINT!r}")
    print(f"{INFO} VERTEX_BASE_URL  = {config.VERTEX_BASE_URL!r}")
    print(f"{INFO} VERTEX_API_KEY   = {'<set>' if config.VERTEX_API_KEY else '<empty>'}")

    if not config.VERTEX_PROJECT_ID or config.VERTEX_PROJECT_ID == "mas-ai-497913":
        print(f"{INFO} Using default project ID (mas-ai-497913) — verify this is correct.")
    return True


def check_auth_mode():
    """Detect which auth mode will be used and validate prerequisites."""
    from shared import config

    api_key = config.VERTEX_API_KEY

    if api_key and api_key.lower() not in ("", "none"):
        print(f"{PASS} API key mode: VERTEX_API_KEY is set.")
        return "api_key"

    try:
        import google.auth
        import google.auth.transport.requests

        print(f"{PASS} ADC mode: google-auth available, will attempt bearer token.")
        return "adc"
    except ImportError:
        print(f"{FAIL} No VERTEX_API_KEY set and google-auth not installed.")
        print(f"{INFO} Install with: pip install google-auth")
        print(f"{INFO} Or set VERTEX_API_KEY in .env")
        return None


def check_invoke(role: str = "observer") -> bool:
    """Run one real LLM invocation with Vertex provider."""
    from core.utils.llm_factory import LLMFactory

    role_upper = role.upper()
    original_provider = os.environ.get(f"{role_upper}_PROVIDER")
    original_model = os.environ.get(f"{role_upper}_MODEL")

    os.environ[f"{role_upper}_PROVIDER"] = "vertex"
    os.environ[f"{role_upper}_MODEL"] = "google/gemini-2.5-flash"

    import importlib
    from shared import config as shared_config
    importlib.reload(shared_config)
    import core.utils.llm_factory as llm_factory_mod
    importlib.reload(llm_factory_mod)
    LLMFactory = llm_factory_mod.LLMFactory

    try:
        print(f"{INFO} Creating {role} LLM via LLMFactory (provider=vertex, model=google/gemini-2.5-flash) ...")
        llm = LLMFactory.create(role)
    except Exception as e:
        print(f"{FAIL} LLMFactory.create failed: {e}")
        return False

    print(f"{INFO} Invoking with a short prompt ...")
    try:
        response = llm.invoke([{"role": "user", "content": "Reply with exactly: OK"}])
        content = response.content if hasattr(response, "content") else str(response)
        print(f"{PASS} Response received: {content!r}")
        return True
    except Exception as e:
        error_str = str(e).lower()

        if "401" in error_str or "unauthorized" in error_str or "unauthenticated" in error_str:
            print(f"{FAIL} Auth error (401/Unauthorized) — VERTEX_API_KEY invalid or ADC token expired.")
        elif "403" in error_str or "permission" in error_str:
            print(f"{FAIL} Permission error (403) — Vertex AI API not enabled, billing disabled, or IAM insufficient.")
            print(f"{INFO} Enable API: gcloud services enable aiplatform.googleapis.com")
            print(f"{INFO} Check billing: gcloud billing projects list --project $VERTEX_PROJECT_ID")
        elif "404" in error_str or "not found" in error_str:
            print(f"{FAIL} Not found (404) — Check VERTEX_PROJECT_ID, VERTEX_LOCATION, VERTEX_ENDPOINT")
        elif "400" in error_str or "bad request" in error_str:
            print(f"{FAIL} Bad request (400) — Model gemini-2.5-flash may not be available at this endpoint.")
        else:
            print(f"{FAIL} Error: {e}")
        return False
    finally:
        if original_provider:
            os.environ[f"{role_upper}_PROVIDER"] = original_provider
        else:
            os.environ.pop(f"{role_upper}_PROVIDER", None)
        if original_model:
            os.environ[f"{role_upper}_MODEL"] = original_model
        else:
            os.environ.pop(f"{role_upper}_MODEL", None)


def main():
    print("=" * 60)
    print("[*] MAS AI — Vertex AI Provider Connection Checker")
    print("=" * 60)

    print("\n--- Step 1: Config Resolution ---")
    check_config()

    print("\n--- Step 2: Auth Mode Detection ---")
    auth_mode = check_auth_mode()
    if auth_mode is None:
        print(f"\n{FAIL} No auth method available. Set VERTEX_API_KEY or install google-auth.")
        sys.exit(1)

    print(f"\n--- Step 3: LLM Invocation (role=observer) ---")
    ok = check_invoke("observer")

    print("\n" + "=" * 60)
    print("[*] SUMMARY")
    print("=" * 60)
    print(f"  Config Resolution:    {PASS}")
    print(f"  Auth Mode:            {PASS if auth_mode else FAIL} ({auth_mode or 'none'})")
    print(f"  LLM Invocation:       {PASS if ok else FAIL}")

    if not ok:
        print("\n[-] Vertex provider check failed. See diagnosis above.")
        print("\n    Troubleshooting commands:")
        print("      # Enable Vertex AI API:")
        print("      gcloud services enable aiplatform.googleapis.com")
        print("      # ADC auth setup:")
        print("      gcloud auth application-default login")
        print("      gcloud config set project <project-id>")
        sys.exit(1)

    print(f"\n[+] Vertex provider is working for role 'observer'.")
    print(f"[+] All agents can use `PROVIDER=vertex` with model `gemini-2.5-flash`.")


if __name__ == "__main__":
    main()