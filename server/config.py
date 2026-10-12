"""Configuration for the data server. Reads the .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CACHE_DIR = ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LIVE_DIR = ROOT / "data" / "live"
LIVE_DIR.mkdir(parents=True, exist_ok=True)

SERVER_PORT = int(os.getenv("SERVER_PORT", "5001"))
BUILDER_TOKEN = os.getenv("BUILDER_TOKEN", "")

# Limits for registered functions.
RUN_TIMEOUT_S = int(os.getenv("RUN_TIMEOUT_S", "600"))
RUN_MEMORY_BYTES = 2 * 1024**3
RUN_CPU_S = 150
