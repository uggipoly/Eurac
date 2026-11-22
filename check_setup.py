"""Verifica rapida del setup: import delle librerie e lettura di .env."""
import sys
from pathlib import Path

# rende importabile il pacchetto in src/ da qualunque cartella si lanci lo script
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from eurac_agent import config  # noqa: E402

print("Python:", sys.version.split()[0])
for mod in ["requests", "ddgs", "trafilatura", "pydantic", "dotenv", "google.genai"]:
    try:
        __import__(mod)
        print(f"  ok  {mod}")
    except ImportError as e:
        print(f"  KO  {mod}: {e}")

print("ROOT:", config.ROOT)
print("GEMINI_API_KEY:", "presente" if config.get_key("GEMINI_API_KEY") else "MANCANTE (vedi README)")
print("Modelli:", config.GEMINI_MODEL, "+ riserve", config.GEMINI_FALLBACK_MODELS)
