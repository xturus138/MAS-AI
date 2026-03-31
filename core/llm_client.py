from langchain_openai import ChatOpenAI
import config

def get_shared_llm():
    # 1. INITIALIZE LANGCHAIN CHATOPENAI WITH OPENROUTER BASE URL
    llm = ChatOpenAI(
        model=config.VISION_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://localhost", 
            "X-Title": "MAS-Agent"
        }
    )
    return llm