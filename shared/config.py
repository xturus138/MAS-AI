import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Device Configuration
TARGET_DEVICE = os.getenv("TARGET_DEVICE", "T8SGEE5TF695ZPV4")

# LLM Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4000"))

# Base Models
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-3-flash-preview")
LOCAL_VISION_MODEL = os.getenv("LOCAL_VISION_MODEL", "gemma3:4b")

# Role-specific Models (Hybrid Mapping)
STRATEGIC_MODEL = os.getenv("STRATEGIC_MODEL", VISION_MODEL)  # Orchestrator & Decider
PERCEPTION_MODEL = os.getenv("PERCEPTION_MODEL", LOCAL_VISION_MODEL) # Observer

# Local Adapter Config
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")

# System Configuration
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")