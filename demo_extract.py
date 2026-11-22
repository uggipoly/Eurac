"""Prova dell'estrattore (passo 3).

Uso:
    python demo_extract.py                 # 3 casi di test (2003, 2022, film = falso positivo)
    python demo_extract.py URL             # un articolo qualsiasi dal web
    python demo_extract.py wayback URL TIMESTAMP

Ogni risultato viene anche salvato, una riga JSON per articolo, in logs/estrazioni.jsonl.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from eurac_agent import config, tools  # noqa: E402
from eurac_agent.extractor import extract_from_article  # noqa: E402

# Casi di test: (descrizione, funzione che scarica l'articolo)
CASES = [
    ("Repubblica 2003 via Wayback (atteso: pertinente, impatti agricoltura/idroelettrico sul Po)",
     lambda: tools.wayback_fetch(
         "http://www.repubblica.it:80/2003/g/sezioni/cronaca/siccita/siccita/siccita.html", "20030811093218")),
    ("il Dolomiti 2022 (atteso: pertinente, impatti in Trentino)",
     lambda: tools.fetch_article(
         "https://www.ildolomiti.it/ambiente/2022/siccita-senza-pioggia-e-crisi-per-diversi-comuni-di-montagna-in-poche-settimane-massima-attenzione-in-trentino-pescatori-al-lavoro-per-salvare-i-pesci-bloccati-nellacqua-calda")),
    ("Film 'Siccità' di Virzì (atteso: NON pertinente)",
     lambda: tools.fetch_article("https://www.mymovies.it/film/2022/siccita/")),
]


def run(label: str, article: dict) -> None:
    print(f"\n{'=' * 80}\n{label}\n  {article.get('url')}")
    if not article.get("ok"):
        print("  download/estrazione testo fallita:", article.get("error"))
        return
    print(f"  {article.get('title')} | {article.get('date')} | {article.get('sitename')}")

    res = extract_from_article(article)
    log(article, res)
    if not res["ok"]:
        print("  ERRORE LLM:", res["error"])
        return

    r = res["result"]
    print(f"  pertinente={r['pertinente']}  has_impact={r['has_impact']}  paese={r['hazard_country']}")
    print(f"  motivo: {r['motivo']}")
    for i in r["impatti"]:
        luogo = ", ".join(v for v in i["luogo"].values() if v)
        print(f"  - [{i['settore']}] {luogo} | {i['periodo']} ({i['anno_inizio']}-{i['anno_fine']})")
        print(f"      {i['descrizione']}")
        print(f"      evidenza: \"{i['evidenza'][:160]}\"")
    print(f"  modello: {res['model']}  token: {res['usage']}")


def log(article: dict, res: dict) -> None:
    """Aggiunge una riga al log JSONL (niente testo integrale: solo metadati + estrazione)."""
    config.LOGS_DIR.mkdir(exist_ok=True)
    row = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "url": article.get("url"), "title": article.get("title"), "date": article.get("date"),
        "sitename": article.get("sitename"), **res,
    }
    with open(config.LOGS_DIR / "estrazioni.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if not config.get_key("GEMINI_API_KEY"):
        sys.exit("Manca GEMINI_API_KEY nel file .env: creala su https://aistudio.google.com/apikey")
    args = sys.argv[1:]
    if not args:
        for label, get in CASES:
            run(label, get())
    elif args[0] == "wayback":
        run("Wayback", tools.wayback_fetch(args[1], args[2]))
    else:
        run("Articolo", tools.fetch_article(args[0]))
