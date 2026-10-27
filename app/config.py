import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATASET = ROOT / os.getenv("DATASET_DIR", "Dataset")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://rag:rag_local_only@localhost:5433/rag"
)
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5.4-mini-2026-03-17")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
DIMENSIONS = 1536