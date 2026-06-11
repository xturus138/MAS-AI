import os
from typing import Any, Dict, List, Optional
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from core.ports.llm_port import ILLMClient
from core.utils.llm_logger import LLMJsonLogger
from shared import config


class LangChainAdapter(ILLMClient):
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

        self.logger = LLMJsonLogger(log_dir=log_dir or os.path.join(config.OUTPUT_DIR, "llm_logs"), session_id=None if log_dir else session_id, model_name=model_name)

        # Azure OpenAI requires special handling
        if provider == "azure" and azure_deployment:
            self.llm = AzureChatOpenAI(
                azure_endpoint=base_url or config.AZURE_OPENAI_ENDPOINT,
                azure_deployment=azure_deployment,
                api_key=api_key,
                api_version=config.AZURE_OPENAI_API_VERSION,
                max_tokens=config.MAX_TOKENS,
                callbacks=[self.logger],
            )
        # Vertex AI: auth is in headers (bearer token for ADC) or ?key= query param
        if provider == "vertex":
            self.llm = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=config.MAX_TOKENS,
                callbacks=[self.logger],
                default_headers=extra_headers,
            )
        else:
            self.llm = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=config.MAX_TOKENS,
                callbacks=[self.logger],
                default_headers=extra_headers or None,
            )

    def invoke(self, messages: List[Any], **kwargs) -> Any:
        return self.llm.invoke(messages, **kwargs)

    def with_structured_output(self, schema: Any) -> Any:
        return self.llm.with_structured_output(schema)

    def stream(self, messages: List[Any], **kwargs) -> Any:
        return self.llm.stream(messages, **kwargs)
