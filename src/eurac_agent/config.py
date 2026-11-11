"""Configurazione: legge .env e definisce i percorsi del progetto."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"

load_dotenv(ROOT / ".env")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip()


def get_key(name: str) -> str | None:
    """Return the API key or None if not found."""
    value = os.getenv(name, "").strip()
    return value or None
