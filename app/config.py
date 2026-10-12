"""Configuration for the user interface."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

APP_PORT = int(os.getenv("APP_PORT", "5000"))
SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:5001").rstrip("/")
BUILDER_URL = os.getenv("BUILDER_URL", "http://127.0.0.1:5002").rstrip("/")
PROXY_TIMEOUT_S = int(os.getenv("PROXY_TIMEOUT_S", "900"))
