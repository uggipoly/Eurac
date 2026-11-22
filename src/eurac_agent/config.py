"""Configurazione: legge .env e definisce i percorsi del progetto."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"

load_dotenv(ROOT / ".env")

# modello principale e modelli di riserva (usati se il principale non risponde)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
GEMINI_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite").split(",")
    if m.strip()
]


def get_key(name: str) -> str | None:
    """Restituisce la chiave API, o None se non è impostata."""
    value = os.getenv(name, "").strip()
    return value or None
