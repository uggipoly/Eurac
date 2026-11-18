"""Prova degli strumenti del passo 2.

Uso:
    python demo_tools.py                       # demo completa
    python demo_tools.py search "siccità Trentino 2022"
    python demo_tools.py fetch URL
    python demo_tools.py wayback "repubblica.it/2003/*" 2003 2007 ".*siccit.*"
"""
import sys
from pathlib import Path

# rende importabile il pacchetto in src/ da qualunque cartella si lanci lo script
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from eurac_agent import tools  # noqa: E402


def show_search(q):
    print(f"\n== Ricerca web: {q!r}")
    res = tools.search_web(q, max_results=5)
    for r in res:
        print(" -", r.get("title"), "\n  ", r.get("url"), r.get("error", ""))
    return res


def show_fetch(url):
    print(f"\n== Articolo: {url}")
    a = tools.fetch_article(url)
    if not a["ok"]:
        print("  KO:", a["error"])
        return a
    print(f"  titolo: {a['title']}\n  data: {a['date']}  testata: {a['sitename']}")
    print(f"  testo ({len(a['text'])} caratteri): {a['text'][:400]}...")
    return a


def show_wayback(pattern, y1=None, y2=None, rx=None):
    print(f"\n== Wayback: {pattern} {y1}-{y2} regex={rx}")
    res = tools.wayback_search(pattern, y1 and int(y1), y2 and int(y2), rx, limit=10)
    for r in res:
        print(" -", r.get("capture_date"), r.get("url"), r.get("error", ""))
    return res


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        res = show_search("siccità Trentino agricoltura 2022")
        first = next((r["url"] for r in res if r.get("url")), None)
        if first:
            show_fetch(first)
        wb = show_wayback("repubblica.it/2003/*", None, None, ".*siccit.*")
        if wb and "error" not in wb[0]:
            print("\n== Estrazione dalla Wayback del primo risultato")
            a = tools.wayback_fetch(wb[0]["url"], wb[0]["timestamp"])
            print("  ok" if a["ok"] else f"  KO: {a['error']}", a.get("title"), a.get("date"))
    elif args[0] == "search":
        show_search(" ".join(args[1:]))
    elif args[0] == "fetch":
        show_fetch(args[1])
    elif args[0] == "wayback":
        show_wayback(*args[1:])
