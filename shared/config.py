import os
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", os.getenv("HF_HUB_DOWNLOAD_TIMEOUT", "300"))
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", os.getenv("HF_HUB_ETAG_TIMEOUT", "300"))

TARGET_DEVICE = os.getenv("TARGET_DEVICE", "T8SGEE5TF695ZPV4")

OUTPUT_DIR    = os.getenv("OUTPUT_DIR", "outputs")
MAX_TOKENS    = int(os.getenv("MAX_TOKENS", "4000"))
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")

NINEROUTER_BASE_URL = os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1")
NINEROUTER_API_KEY = os.getenv("NINEROUTER_API_KEY", "not-needed-for-local")
NINEROUTER_MODEL = os.getenv("NINEROUTER_MODEL", "MAS-AI")

CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "")
CURSOR_BASE_URL = os.getenv("CURSOR_BASE_URL", "https://api2.cursor.sh")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://masaiskripsi.openai.azure.com/openai/v1")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")

BLUESMINDS_API_KEY = os.getenv("BLUESMINDS_API_KEY", "")
BLUESMINDS_BASE_URL = os.getenv("BLUESMINDS_BASE_URL", "https://api.bluesminds.com/v1")

LLM7_API_KEY = os.getenv("LLM7_API_KEY", "")
LLM7_BASE_URL = os.getenv("LLM7_BASE_URL", "https://api.llm7.io/v1")

ALIBABA_API_KEY = os.getenv("ALIBABA_API_KEY", "")
ALIBABA_BASE_URL = os.getenv("ALIBABA_BASE_URL", "https://ws-uzp67h5dtqgxfa3h.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")

VERTEX_PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "mas-ai-497913")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "global")
VERTEX_ENDPOINT = os.getenv("VERTEX_ENDPOINT", "openapi")
VERTEX_API_KEY = os.getenv("VERTEX_API_KEY", "")
VERTEX_BASE_URL = (
    f"https://aiplatform.googleapis.com/v1beta1/projects/"
    f"{VERTEX_PROJECT_ID}/locations/{VERTEX_LOCATION}/endpoints/{VERTEX_ENDPOINT}"
)

PROVIDER_URLS: dict = {
    "openrouter": "https://openrouter.ai/api/v1",
    "blackbox":   "https://api.blackbox.ai/v1",
    "openai":     "https://api.openai.com/v1",
    "cursor":     CURSOR_BASE_URL,
    "vertex":     VERTEX_BASE_URL,
    "alibaba":    ALIBABA_BASE_URL,
    "llm7":       LLM7_BASE_URL,
    "bluesminds": BLUESMINDS_BASE_URL,
    "local":      os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"),
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/",
    "google":     "https://generativelanguage.googleapis.com/v1beta/openai/",
    "9router":    os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1"),
    "azure":      AZURE_OPENAI_ENDPOINT if AZURE_OPENAI_ENDPOINT else "",
}

def _resolve_api_key(provider: str, key_env_var: str) -> str:
    key = os.getenv(key_env_var)
    if key and key.lower() != "none":
        return key
    
    provider_key_var = f"{provider.upper()}_API_KEY"
    provider_key = os.getenv(provider_key_var)
    if provider_key and provider_key.lower() != "none":
        return provider_key

    if provider in ("gemini", "google"):
        for alt_var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            alt_key = os.getenv(alt_var)
            if alt_key and alt_key.lower() != "none":
                return alt_key

    if provider == "9router":
        return os.getenv("9ROUTER_API_KEY", "not-needed-for-local")

    if provider == "vertex":
        return os.getenv("VERTEX_API_KEY", "")

    if provider == "alibaba":
        return os.getenv("ALIBABA_API_KEY", "")

    if provider == "llm7":
        return os.getenv("LLM7_API_KEY", "")

    if provider == "bluesminds":
        return os.getenv("BLUESMINDS_API_KEY", "")

    return os.getenv("OPENROUTER_API_KEY", "none")

OBSERVER_PROVIDER = os.getenv("OBSERVER_PROVIDER", "openrouter").lower()
OBSERVER_API_KEY  = _resolve_api_key(OBSERVER_PROVIDER, "OBSERVER_API_KEY")
OBSERVER_BASE_URL = os.getenv("OBSERVER_BASE_URL", PROVIDER_URLS.get(OBSERVER_PROVIDER, "https://openrouter.ai/api/v1"))
OBSERVER_MODEL    = os.getenv("OBSERVER_MODEL", "google/gemini-2.0-flash-001")
OBSERVER_AZURE_DEPLOYMENT = os.getenv("OBSERVER_AZURE_DEPLOYMENT", "")

DECIDER_PROVIDER = os.getenv("DECIDER_PROVIDER", "openrouter").lower()
DECIDER_API_KEY  = _resolve_api_key(DECIDER_PROVIDER, "DECIDER_API_KEY")
DECIDER_MODEL    = os.getenv("DECIDER_MODEL", "liquid/lfm-2.5-1.2b-thinking:free")
DECIDER_BASE_URL = os.getenv("DECIDER_BASE_URL", PROVIDER_URLS.get(DECIDER_PROVIDER, "https://openrouter.ai/api/v1"))
DECIDER_AZURE_DEPLOYMENT = os.getenv("DECIDER_AZURE_DEPLOYMENT", "")

REFLECTOR_PROVIDER = os.getenv("REFLECTOR_PROVIDER", "openrouter").lower()
REFLECTOR_API_KEY  = _resolve_api_key(REFLECTOR_PROVIDER, "REFLECTOR_API_KEY")
REFLECTOR_BASE_URL = os.getenv("REFLECTOR_BASE_URL", PROVIDER_URLS.get(REFLECTOR_PROVIDER, "https://openrouter.ai/api/v1"))
REFLECTOR_MODEL    = os.getenv("REFLECTOR_MODEL", "qwen/qwen-2.5-72b-instruct")
REFLECTOR_AZURE_DEPLOYMENT = os.getenv("REFLECTOR_AZURE_DEPLOYMENT", "")

ORCHESTRATOR_PROVIDER = os.getenv("ORCHESTRATOR_PROVIDER", "blackbox").lower()
ORCHESTRATOR_API_KEY  = _resolve_api_key(ORCHESTRATOR_PROVIDER, "ORCHESTRATOR_API_KEY")
ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", PROVIDER_URLS.get(ORCHESTRATOR_PROVIDER, "https://openrouter.ai/api/v1"))
ORCHESTRATOR_MODEL    = os.getenv("ORCHESTRATOR_MODEL", "blackboxai/google/gemini-3.1-flash")
ORCHESTRATOR_AZURE_DEPLOYMENT = os.getenv("ORCHESTRATOR_AZURE_DEPLOYMENT", "")

FIGMA_ACCESS_TOKEN = os.getenv("FIGMA_ACCESS_TOKEN", "")
FIGMA_API_BASE     = os.getenv("FIGMA_API_BASE", "https://api.figma.com/v1")
FIGMA_FILE_URL     = os.getenv("FIGMA_URL_QA", "")
FIGMA_REQUEST_TIMEOUT = int(os.getenv("FIGMA_REQUEST_TIMEOUT", "300"))

OBSERVER_MODE = os.getenv("OBSERVER_MODE", "xml_first").lower()

print(f"[*] Environment Loaded:")
print(f"    - Observer Mode:      {OBSERVER_MODE}")
print(f"    - Observer Model:     {OBSERVER_MODEL}")
print(f"    - Decider Model:      {DECIDER_MODEL}")
print(f"    - Reflector Model:    {REFLECTOR_MODEL}")
print(f"    - Orchestrator Model: {ORCHESTRATOR_MODEL}")
print(f"    - Max Tokens:         {MAX_TOKENS}")

TOKEN_CONTEXT_WINDOW = int(os.getenv("TOKEN_CONTEXT_WINDOW", "32768"))
TOKEN_WARN_THRESHOLD = float(os.getenv("TOKEN_WARN_THRESHOLD", "0.75"))

WORKFLOW_STRATEGY = os.getenv("WORKFLOW_STRATEGY", "predefined").lower()

ADAPTIVE_EXECUTOR_WAIT = os.getenv("ADAPTIVE_EXECUTOR_WAIT", "true").lower() == "true"
PARALLEL_REFLECTOR_CHECKS = os.getenv("PARALLEL_REFLECTOR_CHECKS", "true").lower() == "true"
OBSERVER_CACHE_ENABLED = os.getenv("OBSERVER_CACHE_ENABLED", "true").lower() == "true"

# --- Observer DSE uncertainty (Phase 1: measurement only) ---
OBSERVER_UNCERTAINTY_ENABLED = os.getenv("OBSERVER_UNCERTAINTY_ENABLED", "false").lower() == "true"
OBSERVER_UNCERTAINTY_SAMPLES = int(os.getenv("OBSERVER_UNCERTAINTY_SAMPLES", "5"))
# Provisional, literature-inspired value. NOT validated. See docs/observer-uncertainty.md.
OBSERVER_UNCERTAINTY_TEMPERATURE = float(os.getenv("OBSERVER_UNCERTAINTY_TEMPERATURE", "1.0"))
# Cost cap: entailment clustering issues up to 2 judge calls per (sample, existing cluster)
# per widget. Widgets beyond this count are skipped and recorded, not silently dropped.
OBSERVER_UNCERTAINTY_MAX_WIDGETS = int(os.getenv("OBSERVER_UNCERTAINTY_MAX_WIDGETS", "20"))
