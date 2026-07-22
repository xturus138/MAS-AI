from shared import config
from adapters.llm.langchain_adapter import LangChainAdapter

try:
    import google.auth
    import google.auth.transport.requests
    _HAS_GOOGLE_AUTH = True
except ImportError:
    _HAS_GOOGLE_AUTH = False


class LLMFactory:
    _ROLE_MAP = {
        "observer": {
            "provider":       lambda: config.OBSERVER_PROVIDER,
            "api_key":        lambda: config.OBSERVER_API_KEY,
            "base_url":       lambda: config.OBSERVER_BASE_URL,
            "model":          lambda: config.OBSERVER_MODEL,
            "azure_deployment": lambda: config.OBSERVER_AZURE_DEPLOYMENT,
        },
        "decider": {
            "provider":       lambda: config.DECIDER_PROVIDER,
            "api_key":        lambda: config.DECIDER_API_KEY,
            "base_url":       lambda: config.DECIDER_BASE_URL,
            "model":          lambda: config.DECIDER_MODEL,
            "azure_deployment": lambda: config.DECIDER_AZURE_DEPLOYMENT,
        },
        "reflector": {
            "provider":       lambda: config.REFLECTOR_PROVIDER,
            "api_key":        lambda: config.REFLECTOR_API_KEY,
            "base_url":       lambda: config.REFLECTOR_BASE_URL,
            "model":          lambda: config.REFLECTOR_MODEL,
            "azure_deployment": lambda: config.REFLECTOR_AZURE_DEPLOYMENT,
        },
        "orchestrator": {
            "provider":       lambda: config.ORCHESTRATOR_PROVIDER,
            "api_key":        lambda: config.ORCHESTRATOR_API_KEY,
            "base_url":       lambda: config.ORCHESTRATOR_BASE_URL,
            "model":          lambda: config.ORCHESTRATOR_MODEL,
            "azure_deployment": lambda: config.ORCHESTRATOR_AZURE_DEPLOYMENT,
        },
    }

    @classmethod
    def create(cls, role: str, session_id: str | None = None, log_dir: str | None = None) -> LangChainAdapter:
        role = role.lower()
        if role not in cls._ROLE_MAP:
            raise ValueError(
                f"[LLMFactory] Unknown role '{role}'. "
                f"Supported roles: {list(cls._ROLE_MAP.keys())}"
            )

        cfg      = cls._ROLE_MAP[role]
        provider = cfg["provider"]()
        api_key  = cfg["api_key"]()
        base_url = cfg["base_url"]()
        model    = cfg["model"]()
        azure_deployment = cfg.get("azure_deployment", lambda: "")() if provider == "azure" else None
        is_local = provider == "local"

        extra_headers = None
        if provider == "openrouter":
            extra_headers = {
                "HTTP-Referer": "https://localhost",
                "X-Title": "MAS-Agent",
            }
        elif provider == "vertex":
            if "/" not in model:
                model = f"google/{model}"
            if api_key and api_key.lower() not in ("", "none"):
                separator = "&" if "?" in base_url else "?"
                base_url = f"{base_url}{separator}key={api_key}"
                api_key = "unused-vertex-api-key"
                extra_headers = {}
            elif _HAS_GOOGLE_AUTH:
                try:
                    credentials, _ = google.auth.default(
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                    credentials.refresh(google.auth.transport.requests.Request())
                    extra_headers = {"Authorization": f"Bearer {credentials.token}"}
                except Exception:
                    print("[LLMFactory] Vertex ADC token refresh failed; falling back to API-key mode with empty key")
                    extra_headers = {}
            else:
                print("[LLMFactory] Vertex: no API key and google-auth unavailable; pass empty headers")
                extra_headers = {}

        print(
            f"[LLMFactory] Creating '{role}' client | "
            f"Provider: {provider} | Model: {model} | "
            f"URL: {base_url}"
        )

        return LangChainAdapter(
            model_name=model,
            api_key=api_key,
            base_url=base_url,
            is_local=is_local,
            session_id=session_id,
            log_dir=log_dir,
            extra_headers=extra_headers,
            provider=provider,
            azure_deployment=azure_deployment,
        )
