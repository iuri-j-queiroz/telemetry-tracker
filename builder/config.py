"""Configuration for the builder service."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BUILDER_PORT = int(os.getenv("BUILDER_PORT", "5002"))
SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:5001").rstrip("/")
BUILDER_TOKEN = os.getenv("BUILDER_TOKEN", "")

LLM_MOCK = os.getenv("LLM_MOCK", "1").strip() not in ("", "0", "false", "False")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

REQUEST_TIMEOUT_S = int(os.getenv("BUILDER_REQUEST_TIMEOUT_S", "900"))
MAX_ATTEMPTS = 3

SCREENS_DIR = Path(__file__).resolve().parent / "screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)
AGENT_MD = ROOT / "agent.md"
