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

OBSERVER_PROVIDER = os.getenv("OBSERVER_PROVIDER", "openrouter").lower()
OBSERVER_API_KEY  = os.getenv("OBSERVER_API_KEY", os.getenv("OPENROUTER_API_KEY", "none"))
OBSERVER_BASE_URL = os.getenv("OBSERVER_BASE_URL", PROVIDER_URLS.get(OBSERVER_PROVIDER, "https://openrouter.ai/api/v1"))
OBSERVER_MODEL    = os.getenv("OBSERVER_MODEL", "google/gemini-2.0-flash-001")

DECIDER_PROVIDER = os.getenv("DECIDER_PROVIDER", "openrouter").lower()
DECIDER_API_KEY  = os.getenv("DECIDER_API_KEY", os.getenv("OPENROUTER_API_KEY", "none"))
DECIDER_MODEL    = os.getenv("DECIDER_MODEL", "liquid/lfm-2.5-1.2b-thinking:free")
DECIDER_BASE_URL = os.getenv("DECIDER_BASE_URL", PROVIDER_URLS.get(DECIDER_PROVIDER, "https://openrouter.ai/api/v1"))

REFLECTOR_PROVIDER = os.getenv("REFLECTOR_PROVIDER", "openrouter").lower()
REFLECTOR_API_KEY  = os.getenv("REFLECTOR_API_KEY", os.getenv("OPENROUTER_API_KEY", "none"))
REFLECTOR_BASE_URL = os.getenv("REFLECTOR_BASE_URL", PROVIDER_URLS.get(REFLECTOR_PROVIDER, "https://openrouter.ai/api/v1"))
REFLECTOR_MODEL    = os.getenv("REFLECTOR_MODEL", "qwen/qwen-2.5-72b-instruct")

ORCHESTRATOR_PROVIDER = os.getenv("ORCHESTRATOR_PROVIDER", "blackbox").lower()
ORCHESTRATOR_API_KEY  = os.getenv("ORCHESTRATOR_API_KEY", os.getenv("OPENROUTER_API_KEY", "none"))
ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", PROVIDER_URLS.get(ORCHESTRATOR_PROVIDER, "https://openrouter.ai/api/v1"))
ORCHESTRATOR_MODEL    = os.getenv("ORCHESTRATOR_MODEL", "blackboxai/google/gemini-3.1-flash")

FIGMA_ACCESS_TOKEN = os.getenv("FIGMA_ACCESS_TOKEN", "")
FIGMA_API_BASE     = os.getenv("FIGMA_API_BASE", "https://api.figma.com/v1")

print(f"[*] Environment Loaded:")
print(f"    - Observer Model:  {OBSERVER_MODEL}")
print(f"    - Decider Model:   {DECIDER_MODEL}")
print(f"    - Reflector Model: {REFLECTOR_MODEL}")
print(f"    - Max Tokens:      {MAX_TOKENS}")

TOKEN_CONTEXT_WINDOW = int(os.getenv("TOKEN_CONTEXT_WINDOW", "32768"))
TOKEN_WARN_THRESHOLD = float(os.getenv("TOKEN_WARN_THRESHOLD", "0.75"))

WORKFLOW_STRATEGY = os.getenv("WORKFLOW_STRATEGY", "predefined").lower()
