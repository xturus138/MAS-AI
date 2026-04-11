from typing import Any, List, Optional
from langchain_openai import ChatOpenAI
from core.ports.llm_port import ILLMClient
from shared import config

class LangChainAdapter(ILLMClient):
    def __init__(self):
        if config.USE_LOCAL_LLM:
            print(f"[*] Using Local LLM: {config.LOCAL_VISION_MODEL}")
            self.llm = ChatOpenAI(
                model=config.LOCAL_VISION_MODEL,
                api_key="ollama",
                base_url=config.LOCAL_LLM_URL,
                max_tokens=config.MAX_TOKENS,
            )
        else:
            print(f"[*] Using OpenRouter: {config.VISION_MODEL}")
            self.llm = ChatOpenAI(
                model=config.VISION_MODEL,
                api_key=config.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                max_tokens=config.MAX_TOKENS,
                default_headers={
                    "HTTP-Referer": "https://localhost", 
                    "X-Title": "MAS-Agent"
                }
            )

    def invoke(self, messages: List[Any], **kwargs) -> Any:
        return self.llm.invoke(messages, **kwargs)

    def with_structured_output(self, schema: Any) -> Any:
        return self.llm.with_structured_output(schema)