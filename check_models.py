"""
check_models.py — Lists all models available for your Blackbox AI API key.
Usage: python check_models.py
"""

import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("PERCEPTION_API_KEY") or os.getenv("STRATEGIC_API_KEY")
BASE_URL = os.getenv("PERCEPTION_BASE_URL", "https://api.blackbox.ai/v1")

if not API_KEY:
    print("[ERROR] No API key found in .env (PERCEPTION_API_KEY or STRATEGIC_API_KEY)")
    exit(1)

print(f"[*] Querying: {BASE_URL}/models")
print(f"[*] Using key: {API_KEY[:8]}...{API_KEY[-4:]}\n")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

try:
    req = urllib.request.Request(
        f"{BASE_URL}/models",
        headers=headers,
        method="GET"
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read().decode("utf-8")
        data = json.loads(raw)

    models = data.get("data", data) if isinstance(data, dict) else data

    if not models:
        print("[!] No models returned. Raw response:")
        print(raw)
    else:
        print(f"[*] Found {len(models)} model(s):\n")
        print(f"{'#':<4} {'ID':<55} {'Object'}")
        print("-" * 75)
        for i, m in enumerate(models, 1):
            model_id = m.get("id", str(m))
            obj      = m.get("object", "-")
            print(f"{i:<4} {model_id:<55} {obj}")

except urllib.error.HTTPError as e:
    print(f"[ERROR] HTTP {e.code}: {e.read().decode()}")
except urllib.error.URLError as e:
    print(f"[ERROR] Request failed: {e.reason}")
