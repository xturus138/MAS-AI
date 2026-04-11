from langchain_openai import ChatOpenAI
import config

def get_shared_llm():
    if config.USE_LOCAL_LLM:
        print(f"[*] Using Local LLM: {config.LOCAL_VISION_MODEL}")
        llm = ChatOpenAI(
            model=config.LOCAL_VISION_MODEL,
            api_key="ollama",
            base_url=config.LOCAL_LLM_URL,
            max_tokens=config.MAX_TOKENS,
        )
    else:
        print(f"[*] Using OpenRouter: {config.VISION_MODEL}")
        llm = ChatOpenAI(
            model=config.VISION_MODEL,
            api_key=config.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            max_tokens=config.MAX_TOKENS,
            default_headers={
                "HTTP-Referer": "https://localhost", 
                "X-Title": "MAS-Agent"
            }
        )
    return llm