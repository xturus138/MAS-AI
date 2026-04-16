from typing import Any, List, Optional
from langchain_openai import ChatOpenAI
from core.ports.llm_port import ILLMClient
from shared import config

class LangChainAdapter(ILLMClient):
    def __init__(
        self, 
        model_name: str, 
        api_key: str = "none", 
        base_url: Optional[str] = None,
        is_local: bool = False
    ):
        self.model_name = model_name
        self.is_local = is_local
        
        print(f"[*] Initializing LLM: {model_name} (Local: {is_local})")
        
        self.llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            max_tokens=config.MAX_TOKENS,
            default_headers={
                "HTTP-Referer": "https://localhost", 
                "X-Title": "MAS-Agent"
            } if not is_local else None
        )

    def invoke(self, messages: List[Any], **kwargs) -> Any:
        return self.llm.invoke(messages, **kwargs)

    def with_structured_output(self, schema: Any) -> Any:
        return self.llm.with_structured_output(schema)