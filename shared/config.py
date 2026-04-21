import os
from dotenv import load_dotenv

load_dotenv()

TARGET_DEVICE = os.getenv("TARGET_DEVICE", "T8SGEE5TF695ZPV4")

OUTPUT_DIR    = os.getenv("OUTPUT_DIR", "outputs")
MAX_TOKENS    = int(os.getenv("MAX_TOKENS", "4000"))
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")

PROVIDER_URLS: dict = {
    "openrouter": "https://openrouter.ai/api/v1",
    "blackbox":   "https://api.blackbox.ai/v1",
    "openai":     "https://api.openai.com/v1",
    "local":      os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
}

PERCEPTION_PROVIDER = os.getenv("PERCEPTION_PROVIDER", "openrouter").lower()
PERCEPTION_API_KEY  = os.getenv("PERCEPTION_API_KEY", os.getenv("OPENROUTER_API_KEY", "none"))
PERCEPTION_BASE_URL = os.getenv("PERCEPTION_BASE_URL", PROVIDER_URLS.get(PERCEPTION_PROVIDER, "https://openrouter.ai/api/v1"))
PERCEPTION_MODEL    = os.getenv("PERCEPTION_MODEL", "google/gemini-2.0-flash-001")

STRATEGIC_PROVIDER = os.getenv("STRATEGIC_PROVIDER", "openrouter").lower()
STRATEGIC_API_KEY  = os.getenv("STRATEGIC_API_KEY", os.getenv("OPENROUTER_API_KEY", "none"))
STRATEGIC_BASE_URL = os.getenv("STRATEGIC_BASE_URL", PROVIDER_URLS.get(STRATEGIC_PROVIDER, "https://openrouter.ai/api/v1"))
STRATEGIC_MODEL    = os.getenv("STRATEGIC_MODEL", "liquid/lfm-2.5-1.2b-thinking:free")

print(f"[*] Environment Loaded:")
print(f"    - Perception Model: {PERCEPTION_MODEL}")
print(f"    - Strategic Model:  {STRATEGIC_MODEL}")
print(f"    - Max Tokens:       {MAX_TOKENS}")

TOKEN_CONTEXT_WINDOW = int(os.getenv("TOKEN_CONTEXT_WINDOW", "32768"))
TOKEN_WARN_THRESHOLD = float(os.getenv("TOKEN_WARN_THRESHOLD", "0.75"))