import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Device Configuration
TARGET_DEVICE = os.getenv("TARGET_DEVICE", "T8SGEE5TF695ZPV4")

# LLM Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-3-flash-preview")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4000"))

# Local LLM Configuration
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "False").lower() == "true"
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
LOCAL_VISION_MODEL = os.getenv("LOCAL_VISION_MODEL", "qwen2.5vl:3b")

# System Configuration
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")