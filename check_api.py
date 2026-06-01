#!/usr/bin/env python3
"""
MAS AI — Ultimate Zero-Dependency API Key & Model Checker
No installations or 'pip install' needed. Run with standard Python 3.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

# Force UTF-8 encoding on standard output for Windows Unicode compatibility
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ANSI formatting colors
RESET = "\033[0m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[36m"
GRAY = "\033[90m"

# Safe Unicode symbols resolution
try:
    "✔ ✘ ⚠ ℹ ━".encode(sys.stdout.encoding or 'utf-8')
    SUCCESS_ICON = f"{GREEN}✔{RESET}"
    FAILURE_ICON = f"{RED}✘{RESET}"
    WARN_ICON = f"{YELLOW}⚠{RESET}"
    INFO_ICON = f"{BLUE}ℹ{RESET}"
    LINE_CHAR = "━"
except Exception:
    SUCCESS_ICON = f"{GREEN}[OK]{RESET}"
    FAILURE_ICON = f"{RED}[FAIL]{RESET}"
    WARN_ICON = f"{YELLOW}[WARN]{RESET}"
    INFO_ICON = f"{BLUE}[INFO]{RESET}"
    LINE_CHAR = "="

ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def load_env_manually():
    """Loads keys from .env without python-dotenv dependency."""
    # Clean standard environment keys to allow dynamic reload
    env_keys_to_clear = [
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "BLACKBOX_API_KEY",
        "CURSOR_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY",
        "OBSERVER_PROVIDER", "OBSERVER_MODEL",
        "DECIDER_PROVIDER", "DECIDER_MODEL",
        "REFLECTOR_PROVIDER", "REFLECTOR_MODEL",
        "ORCHESTRATOR_PROVIDER", "ORCHESTRATOR_MODEL",
        "LOCAL_LLM_URL"
    ]
    for key in env_keys_to_clear:
        if key in os.environ:
            del os.environ[key]

    if os.path.exists(ENV_FILE_PATH):
        try:
            with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        # Strip comments if present in the line (e.g. KEY=VAL # comment)
                        val_part = v.split("#")[0].strip()
                        # Strip standard quotes if present
                        val = val_part.strip("'\"")
                        os.environ[k.strip()] = val
        except Exception as e:
            print(f" {WARN_ICON} Couldn't read existing .env file: {e}")

def save_key_to_env(env_var_name: str, api_key: str):
    """Saves or updates a key in the .env file in the root."""
    try:
        content = ""
        if os.path.exists(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                content = f.read()

        prefix = f"{env_var_name}="
        if prefix in content:
            lines = content.splitlines()
            new_lines = []
            replaced = False
            for line in lines:
                if line.strip().startswith(prefix):
                    new_lines.append(f"{env_var_name}={api_key}")
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append(f"{env_var_name}={api_key}")
            new_content = "\n".join(new_lines) + "\n"
        else:
            new_content = content
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            new_content += f"\n# Added by check_api.py\n{env_var_name}={api_key}\n"

        with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        print(f"\n {SUCCESS_ICON} {GREEN}Saved {env_var_name} successfully to .env!{RESET}")
        return True
    except Exception as e:
        print(f"\n {FAILURE_ICON} {RED}Error saving key to .env:{RESET} {e}")
        return False

def make_http_request(url, method="GET", headers=None, body=None):
    """Zero-dependency HTTP requester."""
    if headers is None:
        headers = {}
    
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    
    # Custom User-Agent to avoid blocking by some providers
    headers["User-Agent"] = "Mozilla/5.0 (MAS AI API Diagnostics Utility)"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12.0) as response:
            status = response.status
            resp_body = response.read().decode("utf-8")
            try:
                parsed_json = json.loads(resp_body) if resp_body else None
            except Exception:
                parsed_json = resp_body
            return status, parsed_json, None
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8")
        try:
            parsed_json = json.loads(resp_body) if resp_body else None
        except Exception:
            parsed_json = resp_body
        return e.code, parsed_json, str(e)
    except Exception as e:
        return 0, None, str(e)

def test_gemini(api_key: str):
    """Checks direct Google Gemini connectivity and prints available models."""
    border = LINE_CHAR * 68
    print(f"\n{BOLD}{BLUE}{border}{RESET}")
    print(f"{BOLD}{BLUE} Testing Google Gemini API Key Validity...{RESET}")
    print(f"{BOLD}{BLUE}{border}{RESET}")
    print(f" {INFO_ICON} Connecting to Gemini models endpoint...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    start = time.time()
    code, data, err = make_http_request(url, "GET")
    duration = time.time() - start

    if code != 200:
        print(f" {FAILURE_ICON} {RED}Rejected!{RESET} HTTP Status {code}")
        if isinstance(data, dict):
            msg = data.get("error", {}).get("message", "Unknown key validation error.")
            print(f"   {RED}Reason: {msg}{RESET}")
            if "disabled" in msg.lower() or code == 403:
                print(f"\n{BOLD}{YELLOW}   {WARN_ICON} Please enable the API in Google Developer Console:{RESET}")
                print(f"   Go to: {UNDERLINE}{BLUE}https://console.developers.google.com/apis/api/generativelanguage.googleapis.com/overview{RESET}")
        else:
            print(f"   {RED}Reason: {err or data}{RESET}")
        return False

    print(f" {SUCCESS_ICON} {GREEN}API Key is VALID!{RESET} ({duration:.2f}s)")
    
    # Print models
    if isinstance(data, dict) and "models" in data:
        models = data["models"]
        gemini_models = [m for m in models if "gemini" in m.get("name", "").lower()]
        print(f" {INFO_ICON} Authorized for {len(gemini_models)} Gemini configurations.")
        if gemini_models:
            print(f"\n   {BOLD}{'Model Name':<32} | {'Input Limit':<14} | {'Output Limit':<14}{RESET}")
            print(f"   {'-'*32}-+-{'-'*14}-+-{'-'*14}")
            for m in sorted(gemini_models, key=lambda x: x.get("name", "")):
                name = m.get("name", "").replace("models/", "")
                in_limit = m.get("inputTokenLimit", "Unknown")
                out_limit = m.get("outputTokenLimit", "Unknown")
                try:
                    in_str = f"{int(in_limit):,}" if in_limit != "Unknown" else "Unknown"
                except Exception:
                    in_str = str(in_limit)
                try:
                    out_str = f"{int(out_limit):,}" if out_limit != "Unknown" else "Unknown"
                except Exception:
                    out_str = str(out_limit)
                print(f"   {name:<32} | {in_str:<14} | {out_str:<14}")
    
    # 2. Quick test generation
    print(f"\n {INFO_ICON} Testing generation request with 'gemini-2.5-flash'...")
    gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    body = {"contents": [{"parts": [{"text": "Confirm you are alive and working in exactly 5 words."}]}]}
    
    g_code, g_data, g_err = make_http_request(gen_url, "POST", body=body)
    if g_code == 200:
        try:
            text = g_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f" {SUCCESS_ICON} {GREEN}Generation Successful!{RESET}")
            print(f"   {BOLD}Gemini says:{RESET} \"{text}\"")
        except Exception:
            print(f" {SUCCESS_ICON} {GREEN}Connected successfully, response format was different.{RESET}")
    else:
        print(f" {FAILURE_ICON} {RED}Generation failed!{RESET} Status {g_code}")
    
    return True

def test_openai_compatible(provider_name: str, endpoint: str, auth_header: str, model: str, api_key: str):
    """Generic OpenAI compatibility checker."""
    border = LINE_CHAR * 68
    print(f"\n{BOLD}{BLUE}{border}{RESET}")
    print(f"{BOLD}{BLUE} Testing {provider_name} Connectivity...{RESET}")
    print(f"{BOLD}{BLUE}{border}{RESET}")
    
    headers = {
        "Authorization": f"{auth_header} {api_key}" if auth_header else api_key,
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Respond with 'OK' in one word."}],
        "max_tokens": 5
    }
    
    print(f" {INFO_ICON} Connecting to {provider_name} ({model})...")
    start = time.time()
    code, data, err = make_http_request(endpoint, "POST", headers, body)
    duration = time.time() - start

    if code == 200:
        print(f" {SUCCESS_ICON} {GREEN}Connected successfully!{RESET} ({duration:.2f}s)")
        try:
            ans = data["choices"][0]["message"]["content"].strip()
            print(f"   {BOLD}Response Output:{RESET} \"{ans}\"")
        except Exception:
            pass
        return True
    elif code == 401:
        print(f" {FAILURE_ICON} {RED}Unauthorized!{RESET} Check if your API key is correct.")
        return False
    else:
        print(f" {FAILURE_ICON} {RED}Failed!{RESET} HTTP Status {code}")
        print(f"   Reason: {err or data}")
        return False

def test_agent_role_models():
    """Reads Observer, Decider, Reflector, and Orchestrator model choices and checks them all."""
    roles = ["OBSERVER", "DECIDER", "REFLECTOR", "ORCHESTRATOR"]
    border = LINE_CHAR * 68
    print(f"\n{BOLD}{BLUE}{border}{RESET}")
    print(f"{BOLD}{BLUE} Testing Selected Agent Role Models (from .env)...             {RESET}")
    print(f"{BOLD}{BLUE}{border}{RESET}")

    load_env_manually()

    tested_any = False
    for role in roles:
        provider_var = f"{role}_PROVIDER"
        model_var = f"{role}_MODEL"
        
        provider = os.getenv(provider_var)
        model = os.getenv(model_var)
        
        if not provider or not model:
            print(f"\n {WARN_ICON} {role:<12}: Role configuration incomplete (Provider or Model missing in .env).")
            continue
            
        tested_any = True
        provider = provider.strip().lower()
        model = model.strip()
        
        print(f"\n {INFO_ICON} {BOLD}{role}{RESET}: Using provider '{BOLD}{provider}{RESET}' and model '{BOLD}{model}{RESET}'")
        
        api_key = None
        key_var = ""
        endpoint = ""
        auth_header = ""
        is_gemini_direct = False
        is_local = False
        
        if provider in ("gemini", "google"):
            key_var = "GEMINI_API_KEY"
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            is_gemini_direct = True
        elif provider == "blackbox":
            key_var = "BLACKBOX_API_KEY"
            api_key = os.getenv("BLACKBOX_API_KEY")
            endpoint = "https://api.blackbox.ai/v1/chat/completions"
            auth_header = "Bearer"
        elif provider == "cursor":
            key_var = "CURSOR_API_KEY"
            api_key = os.getenv("CURSOR_API_KEY")
            endpoint = "https://api2.cursor.sh/v1/chat/completions"
            auth_header = "Bearer"
        elif provider == "openrouter":
            key_var = "OPENROUTER_API_KEY"
            api_key = os.getenv("OPENROUTER_API_KEY")
            endpoint = "https://openrouter.ai/api/v1/chat/completions"
            auth_header = "Bearer"
        elif provider == "openai":
            key_var = "OPENAI_API_KEY"
            api_key = os.getenv("OPENAI_API_KEY")
            endpoint = "https://api.openai.com/v1/chat/completions"
            auth_header = "Bearer"
        elif provider == "local":
            is_local = True
            base_url = os.getenv("LOCAL_LLM_URL") or "http://localhost:11434/v1"
            endpoint = f"{base_url.rstrip('/')}/chat/completions"
        else:
            print(f"   {FAILURE_ICON} {RED}Unknown Provider '{provider}' for {role}!{RESET}")
            continue

        if not is_local and (not api_key or api_key.strip() == "" or "your_" in api_key):
            print(f"   {FAILURE_ICON} {RED}Failed!{RESET} API Key '{key_var}' is not configured in .env.")
            continue
            
        start_time = time.time()
        if is_gemini_direct:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            body = {"contents": [{"parts": [{"text": "Respond with 'OK' in exactly one word."}]}]}
            code, data, err = make_http_request(url, "POST", body=body)
            duration = time.time() - start_time
            if code == 200:
                try:
                    ans = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    print(f"   {SUCCESS_ICON} {GREEN}Connection Success!{RESET} ({duration:.2f}s) Response: \"{ans}\"")
                except Exception:
                    print(f"   {SUCCESS_ICON} {GREEN}Connection Success!{RESET} ({duration:.2f}s)")
            else:
                print(f"   {FAILURE_ICON} {RED}Failed!{RESET} HTTP Status {code}. Reason: {err or data}")
        else:
            headers = {}
            if api_key:
                headers["Authorization"] = f"{auth_header} {api_key}" if auth_header else api_key
            body = {
                "model": model,
                "messages": [{"role": "user", "content": "Respond with 'OK' in exactly one word."}],
                "max_tokens": 5
            }
            code, data, err = make_http_request(endpoint, "POST", headers, body)
            duration = time.time() - start_time
            if code == 200:
                try:
                    ans = data["choices"][0]["message"]["content"].strip()
                    print(f"   {SUCCESS_ICON} {GREEN}Connection Success!{RESET} ({duration:.2f}s) Response: \"{ans}\"")
                except Exception:
                    print(f"   {SUCCESS_ICON} {GREEN}Connection Success!{RESET} ({duration:.2f}s)")
            else:
                print(f"   {FAILURE_ICON} {RED}Failed!{RESET} HTTP Status {code}. Reason: {err or data}")

    if not tested_any:
        print(f"\n {WARN_ICON} No agent roles were found/tested in your .env.")

def get_key_status(env_var: str):
    """Formated check for environment values."""
    key = os.getenv(env_var)
    if env_var == "GEMINI_API_KEY" and not key:
        key = os.getenv("GOOGLE_API_KEY")
        
    if not key or key.strip() == "" or "your_" in key:
        return f"{GRAY}[Not Configured]{RESET}"
    masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "..."
    return f"{GREEN}[Configured: {masked}]{RESET}"

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    while True:
        # Reload environment
        load_env_manually()
        
        clear_console()
        print(f"{BOLD}{BLUE}===================================================================={RESET}")
        print(f"{BOLD}{BLUE}         MAS AI — PURE ZERO-DEPENDENCY API & MODEL DIAGNOSTIC       {RESET}")
        print(f"{BOLD}{BLUE}===================================================================={RESET}")
        
        gemini_status = get_key_status("GEMINI_API_KEY")
        blackbox_status = get_key_status("BLACKBOX_API_KEY")
        cursor_status = get_key_status("CURSOR_API_KEY")
        openrouter_status = get_key_status("OPENROUTER_API_KEY")
        openai_status = get_key_status("OPENAI_API_KEY")

        print(f"\n  Active configured keys in current .env:")
        print(f"  [{GREEN}1{RESET}] Google Gemini API       {gemini_status}")
        print(f"  [{GREEN}2{RESET}] Blackbox AI API        {blackbox_status}")
        print(f"  [{GREEN}3{RESET}] Cursor API             {cursor_status}")
        print(f"  [{GREEN}4{RESET}] OpenRouter API         {openrouter_status}")
        print(f"  [{GREEN}5{RESET}] OpenAI API             {openai_status}")
        print(f"  [{GREEN}6{RESET}] {BOLD}{YELLOW}Test Configured Agent Role Models (Observer, Decider, etc.){RESET}")
        print(f"  [{GREEN}7{RESET}] Run ALL Provider API Key Checks")
        print(f"  [{GREEN}8{RESET}] {BOLD}{RED}Exit{RESET}")
        print(f"{BOLD}{BLUE}===================================================================={RESET}")
        
        try:
            choice = input(f" {BOLD}Choose an option (1-8): {RESET}").strip()
        except KeyboardInterrupt:
            print("\n Goodbye!")
            break
            
        if choice == "8":
            print("\n Goodbye!")
            break
            
        if choice == "1":
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not key:
                key = input(f"\n {WARN_ICON} Gemini API key not found in .env. Enter it here: ").strip()
                if key:
                    if test_gemini(key):
                        save = input(" Save to your .env? (y/n): ").strip().lower()
                        if save in ("y", "yes"):
                            save_key_to_env("GEMINI_API_KEY", key)
            else:
                test_gemini(key)
                
        elif choice == "2":
            key = os.getenv("BLACKBOX_API_KEY")
            if not key:
                key = input(f"\n {WARN_ICON} Blackbox API key not found in .env. Enter it here: ").strip()
                if key:
                    if test_openai_compatible("Blackbox AI", "https://api.blackbox.ai/v1/chat/completions", "Bearer", "blackboxai/anthropic/claude-sonnet-4.6", key):
                        save = input(" Save to your .env? (y/n): ").strip().lower()
                        if save in ("y", "yes"):
                            save_key_to_env("BLACKBOX_API_KEY", key)
            else:
                test_openai_compatible("Blackbox AI", "https://api.blackbox.ai/v1/chat/completions", "Bearer", "blackboxai/anthropic/claude-sonnet-4.6", key)

        elif choice == "3":
            key = os.getenv("CURSOR_API_KEY")
            if not key:
                key = input(f"\n {WARN_ICON} Cursor API key not found in .env. Enter it here: ").strip()
                if key:
                    if test_openai_compatible("Cursor API", "https://api2.cursor.sh/v1/chat/completions", "Bearer", "cursor-small", key):
                        save = input(" Save to your .env? (y/n): ").strip().lower()
                        if save in ("y", "yes"):
                            save_key_to_env("CURSOR_API_KEY", key)
            else:
                test_openai_compatible("Cursor API", "https://api2.cursor.sh/v1/chat/completions", "Bearer", "cursor-small", key)

        elif choice == "4":
            key = os.getenv("OPENROUTER_API_KEY")
            if not key:
                key = input(f"\n {WARN_ICON} OpenRouter API key not found in .env. Enter it here: ").strip()
                if key:
                    if test_openai_compatible("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "Bearer", "liquid/lfm-2.5-1.2b-thinking:free", key):
                        save = input(" Save to your .env? (y/n): ").strip().lower()
                        if save in ("y", "yes"):
                            save_key_to_env("OPENROUTER_API_KEY", key)
            else:
                test_openai_compatible("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "Bearer", "liquid/lfm-2.5-1.2b-thinking:free", key)

        elif choice == "5":
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                key = input(f"\n {WARN_ICON} OpenAI API key not found in .env. Enter it here: ").strip()
                if key:
                    if test_openai_compatible("OpenAI", "https://api.openai.com/v1/chat/completions", "Bearer", "gpt-4o-mini", key):
                        save = input(" Save to your .env? (y/n): ").strip().lower()
                        if save in ("y", "yes"):
                            save_key_to_env("OPENAI_API_KEY", key)
            else:
                test_openai_compatible("OpenAI", "https://api.openai.com/v1/chat/completions", "Bearer", "gpt-4o-mini", key)

        elif choice == "6":
            test_agent_role_models()

        elif choice == "7":
            # Run all
            g_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if g_key: test_gemini(g_key)
            
            b_key = os.getenv("BLACKBOX_API_KEY")
            if b_key: test_openai_compatible("Blackbox AI", "https://api.blackbox.ai/v1/chat/completions", "Bearer", "blackboxai/anthropic/claude-sonnet-4.6", b_key)
            
            c_key = os.getenv("CURSOR_API_KEY")
            if c_key: test_openai_compatible("Cursor API", "https://api2.cursor.sh/v1/chat/completions", "Bearer", "cursor-small", c_key)
            
            r_key = os.getenv("OPENROUTER_API_KEY")
            if r_key: test_openai_compatible("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "Bearer", "liquid/lfm-2.5-1.2b-thinking:free", r_key)
            
            o_key = os.getenv("OPENAI_API_KEY")
            if o_key: test_openai_compatible("OpenAI", "https://api.openai.com/v1/chat/completions", "Bearer", "gpt-4o-mini", o_key)

        else:
            print(f"\n {FAILURE_ICON} {RED}Invalid Option!{RESET}")
            
        input(f"\n{GRAY}Press Enter to return to main menu...{RESET}")

if __name__ == "__main__":
    main()
