import os
from typing import Any, Dict, List, Optional
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from core.ports.llm_port import ILLMClient
from core.utils.llm_logger import LLMJsonLogger
from shared import config


class LangChainAdapter(ILLMClient):
    """Unified LLM adapter — agents never know which SDK is underneath."""

    def __init__(
        self,
        model_name: str,
        api_key: str = "none",
        base_url: Optional[str] = None,
        is_local: bool = False,
        session_id: Optional[str] = None,
        log_dir: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        provider: str = "openai",
        azure_deployment: Optional[str] = None,
    ):
        self.model_name = model_name
        self.is_local   = is_local
        self.provider   = provider

        self.logger = LLMJsonLogger(
            log_dir=log_dir or os.path.join(config.OUTPUT_DIR, "llm_logs"),
            session_id=None if log_dir else session_id,
            model_name=model_name,
        )

        self.llm = self._build_llm(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            max_tokens=config.MAX_TOKENS,
            extra_headers=extra_headers,
            provider=provider,
            azure_deployment=azure_deployment,
            callbacks=[self.logger],
        )

    # ── SDK selection ─────────────────────────────────────────────────────

    @staticmethod
    def _build_llm(
        model_name: str,
        api_key: str,
        base_url: Optional[str],
        max_tokens: int,
        extra_headers: Optional[Dict[str, str]],
        provider: str,
        azure_deployment: Optional[str],
        callbacks: list,
    ):
        if provider == "azure" and azure_deployment:
            return AzureChatOpenAI(
                azure_endpoint=base_url or config.AZURE_OPENAI_ENDPOINT,
                azure_deployment=azure_deployment,
                api_key=api_key,
                api_version=config.AZURE_OPENAI_API_VERSION,
                max_tokens=max_tokens,
                callbacks=callbacks,
            )

        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=max_tokens,
                callbacks=callbacks,
            )

        # OpenAI-compatible (openai, openrouter, blackbox, vertex, gemini, local, etc.)
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            callbacks=callbacks,
            default_headers=extra_headers or None,
            max_retries=5,
            timeout=60,
        )

    # ── ILLMClient interface ──────────────────────────────────────────────

    def invoke(self, messages: List[Any], **kwargs) -> Any:
        return self.llm.invoke(messages, **kwargs)

    def with_structured_output(self, schema: Any) -> Any:
        return self.llm.with_structured_output(schema, method="function_calling")

    def stream(self, messages: List[Any], **kwargs) -> Any:
        return self.llm.stream(messages, **kwargs)
