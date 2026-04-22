import os
import json
import urllib.request
import urllib.error
from shared import config

def get_headers(provider, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://localhost"
        headers["X-Title"] = "MAS-Agent"
    return headers

def check_endpoint(provider, base_url, api_key):
    if not api_key or api_key.lower() == "none":
        return

    print(f"[*] Querying Provider: {provider} | URL: {base_url}")
    
    headers = get_headers(provider, api_key)
    try:
        req = urllib.request.Request(f"{base_url}/models", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            models = data.get("data", data) if isinstance(data, dict) else data
            
            if not models:
                print(f"[!] No models found in response.")
                return

            print(f"[+] Found {len(models)} models:")
            for i, m in enumerate(models, 1):
                mid = m.get("id", str(m))
                print(f"    {i:<3}. {mid}")
            print("")
            
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"[ERROR] Connection Failed: {str(e)}")

def main():
    print(f"{'='*60}")
    print(f" MODEL AVAILABILITY CHECK ")
    print(f"{'='*60}\n")
    
    seen = set()
    configs = [
        (config.OBSERVER_PROVIDER, config.OBSERVER_BASE_URL, config.OBSERVER_API_KEY),
        (config.DECIDER_PROVIDER, config.DECIDER_BASE_URL, config.DECIDER_API_KEY),
        (config.REFLECTOR_PROVIDER, config.REFLECTOR_BASE_URL, config.REFLECTOR_API_KEY),
    ]
    
    for prov, url, key in configs:
        if (prov, url, key) not in seen:
            check_endpoint(prov, url, key)
            seen.add((prov, url, key))

if __name__ == "__main__":
    main()
