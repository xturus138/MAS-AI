import os
from dotenv import load_dotenv

load_dotenv()

# Suppress noisy third-party warnings before any heavy imports
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

TARGET_DEVICE = os.getenv("TARGET_DEVICE", "T8SGEE5TF695ZPV4")

OUTPUT_DIR    = os.getenv("OUTPUT_DIR", "outputs")
MAX_TOKENS    = int(os.getenv("MAX_TOKENS", "4000"))
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")

CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "")
CURSOR_BASE_URL = os.getenv("CURSOR_BASE_URL", "https://api2.cursor.sh")

PROVIDER_URLS: dict = {
    "openrouter": "https://openrouter.ai/api/v1",
    "blackbox":   "https://api.blackbox.ai/v1",
    "openai":     "https://api.openai.com/v1",
    "cursor":     CURSOR_BASE_URL,
    "local":      os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
    "google":     "https://generativelanguage.googleapis.com/v1beta/openai/",
}

def _resolve_api_key(provider: str, key_env_var: str) -> str:
    key = os.getenv(key_env_var)
    if key and key.lower() != "none":
        return key
    
    provider_key_var = f"{provider.upper()}_API_KEY"
    provider_key = os.getenv(provider_key_var)
    if provider_key and provider_key.lower() != "none":
        return provider_key

    # Robust fallback for Google / Gemini provider keys
    if provider in ("gemini", "google"):
        for alt_var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            alt_key = os.getenv(alt_var)
            if alt_key and alt_key.lower() != "none":
                return alt_key

    return os.getenv("OPENROUTER_API_KEY", "none")

OBSERVER_PROVIDER = os.getenv("OBSERVER_PROVIDER", "openrouter").lower()
OBSERVER_API_KEY  = _resolve_api_key(OBSERVER_PROVIDER, "OBSERVER_API_KEY")
OBSERVER_BASE_URL = os.getenv("OBSERVER_BASE_URL", PROVIDER_URLS.get(OBSERVER_PROVIDER, "https://openrouter.ai/api/v1"))
OBSERVER_MODEL    = os.getenv("OBSERVER_MODEL", "google/gemini-2.0-flash-001")

DECIDER_PROVIDER = os.getenv("DECIDER_PROVIDER", "openrouter").lower()
DECIDER_API_KEY  = _resolve_api_key(DECIDER_PROVIDER, "DECIDER_API_KEY")
DECIDER_MODEL    = os.getenv("DECIDER_MODEL", "liquid/lfm-2.5-1.2b-thinking:free")
DECIDER_BASE_URL = os.getenv("DECIDER_BASE_URL", PROVIDER_URLS.get(DECIDER_PROVIDER, "https://openrouter.ai/api/v1"))

REFLECTOR_PROVIDER = os.getenv("REFLECTOR_PROVIDER", "openrouter").lower()
REFLECTOR_API_KEY  = _resolve_api_key(REFLECTOR_PROVIDER, "REFLECTOR_API_KEY")
REFLECTOR_BASE_URL = os.getenv("REFLECTOR_BASE_URL", PROVIDER_URLS.get(REFLECTOR_PROVIDER, "https://openrouter.ai/api/v1"))
REFLECTOR_MODEL    = os.getenv("REFLECTOR_MODEL", "qwen/qwen-2.5-72b-instruct")

ORCHESTRATOR_PROVIDER = os.getenv("ORCHESTRATOR_PROVIDER", "blackbox").lower()
ORCHESTRATOR_API_KEY  = _resolve_api_key(ORCHESTRATOR_PROVIDER, "ORCHESTRATOR_API_KEY")
ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", PROVIDER_URLS.get(ORCHESTRATOR_PROVIDER, "https://openrouter.ai/api/v1"))
ORCHESTRATOR_MODEL    = os.getenv("ORCHESTRATOR_MODEL", "blackboxai/google/gemini-3.1-flash")

FIGMA_ACCESS_TOKEN = os.getenv("FIGMA_ACCESS_TOKEN", "")
FIGMA_API_BASE     = os.getenv("FIGMA_API_BASE", "https://api.figma.com/v1")
FIGMA_FILE_URL     = os.getenv("FIGMA_URL_QA", "")

# OmniParser Vision Backend
# Set OMNIPARSER_ENABLED=true once model weights are downloaded.
OMNIPARSER_ENABLED       = os.getenv("OMNIPARSER_ENABLED", "false").lower() == "true"
OMNIPARSER_PROJECT_DIR   = os.getenv("OMNIPARSER_PROJECT_DIR", "")
OMNIPARSER_WEIGHTS_DIR   = os.getenv("OMNIPARSER_WEIGHTS_DIR", "")
OMNIPARSER_BOX_THRESHOLD = float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05"))

print(f"[*] Environment Loaded:")
print(f"    - Observer Model:     {OBSERVER_MODEL}")
print(f"    - Decider Model:      {DECIDER_MODEL}")
print(f"    - Reflector Model:    {REFLECTOR_MODEL}")
print(f"    - Orchestrator Model: {ORCHESTRATOR_MODEL}")
print(f"    - Max Tokens:         {MAX_TOKENS}")

TOKEN_CONTEXT_WINDOW = int(os.getenv("TOKEN_CONTEXT_WINDOW", "32768"))
TOKEN_WARN_THRESHOLD = float(os.getenv("TOKEN_WARN_THRESHOLD", "0.75"))

WORKFLOW_STRATEGY = os.getenv("WORKFLOW_STRATEGY", "predefined").lower()
