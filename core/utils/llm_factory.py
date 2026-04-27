from shared import config
from adapters.llm.langchain_adapter import LangChainAdapter


class LLMFactory:
    _ROLE_MAP = {
        "observer": {
            "provider":  lambda: config.OBSERVER_PROVIDER,
            "api_key":   lambda: config.OBSERVER_API_KEY,
            "base_url":  lambda: config.OBSERVER_BASE_URL,
            "model":     lambda: config.OBSERVER_MODEL,
        },
        "decider": {
            "provider":  lambda: config.DECIDER_PROVIDER,
            "api_key":   lambda: config.DECIDER_API_KEY,
            "base_url":  lambda: config.DECIDER_BASE_URL,
            "model":     lambda: config.DECIDER_MODEL,
        },
        "reflector": {
            "provider":  lambda: config.REFLECTOR_PROVIDER,
            "api_key":   lambda: config.REFLECTOR_API_KEY,
            "base_url":  lambda: config.REFLECTOR_BASE_URL,
            "model":     lambda: config.REFLECTOR_MODEL,
        },
        "orchestrator": {
            "provider":  lambda: config.ORCHESTRATOR_PROVIDER,
            "api_key":   lambda: config.ORCHESTRATOR_API_KEY,
            "base_url":  lambda: config.ORCHESTRATOR_BASE_URL,
            "model":     lambda: config.ORCHESTRATOR_MODEL,
        },
    }

    @classmethod
    def create(cls, role: str, session_id: str | None = None) -> LangChainAdapter:
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
        is_local = provider == "local"

        extra_headers = (
            {"HTTP-Referer": "https://localhost", "X-Title": "MAS-Agent"}
            if provider == "openrouter"
            else None
        )

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
            extra_headers=extra_headers,
        )
