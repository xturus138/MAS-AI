from typing import Any, Dict, List, Optional
from langchain_openai import ChatOpenAI
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
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.model_name = model_name
        self.is_local   = is_local

        self.logger = LLMJsonLogger(session_id=session_id, model_name=model_name)

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
