"""Verifica rapida del setup: import delle librerie e lettura di .env."""
import sys
from pathlib import Path

# rende importabile il pacchetto in src/ da qualunque cartella si lanci lo script
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from eurac_agent import config  # noqa: E402

print("Python:", sys.version.split()[0])
for mod in ["requests", "ddgs", "trafilatura", "pydantic", "dotenv"]:
    try:
        __import__(mod)
        print(f"  ok  {mod}")
    except ImportError as e:
        print(f"  KO  {mod}: {e}")

print("ROOT:", config.ROOT)
print("LLM_PROVIDER:", config.LLM_PROVIDER or "(non ancora scelto)")
for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
    print(f"  {k}:", "presente" if config.get_key(k) else "vuota")
