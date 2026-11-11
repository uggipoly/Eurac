"""Strumenti dell'agente: ricerca web, download+estrazione testo, Wayback Machine.

Ogni funzione restituisce dati semplici (dict/list) così l'agente e i log JSONL
possono usarli direttamente.
"""
from __future__ import annotations

import json
import re
import time

import requests
import trafilatura
from ddgs import DDGS

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) eurac-drought-research/0.1"
TIMEOUT = 20

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


# ---------------------------------------------------------------- ricerca web
def search_web(query: str, max_results: int = 10, timelimit: str | None = None) -> list[dict]:
    """Ricerca DuckDuckGo (risultati web generici, regione Italia).

    timelimit: None, 'd', 'w', 'm', 'y' (DDG non supporta intervalli di anni arbitrari).
    """
    try:
        raw = DDGS().text(query, region="it-it", max_results=max_results, timelimit=timelimit)
    except Exception as e:  # ddgs solleva eccezioni per rate limit / nessun risultato
        return [{"error": f"{type(e).__name__}: {e}", "query": query}]
    return [
        {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body"), "source": "ddg_web"}
        for r in raw
    ]


def search_news(query: str, max_results: int = 10, timelimit: str | None = None) -> list[dict]:
    """Ricerca DuckDuckGo News (soprattutto notizie recenti, con data e testata)."""
    try:
        raw = DDGS().news(query, region="it-it", max_results=max_results, timelimit=timelimit)
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}", "query": query}]
    return [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("body"),
            "date": r.get("date"),
            "publisher": r.get("source"),
            "source": "ddg_news",
        }
        for r in raw
    ]


# ------------------------------------------------------- download + estrazione
def fetch_html(url: str) -> str | None:
    try:
        r = _session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException:
        return None
    r.encoding = r.encoding or r.apparent_encoding
    return r.text


def extract_article(html: str, url: str | None = None) -> dict | None:
    """Estrae titolo, data, testata e testo principale con trafilatura."""
    out = trafilatura.extract(
        html, url=url, output_format="json", with_metadata=True,
        include_comments=False, include_tables=False, favor_precision=True,
    )
    if not out:
        return None
    d = json.loads(out)
    return {
        "title": d.get("title"),
        "date": d.get("date"),
        "sitename": d.get("sitename") or d.get("hostname"),
        "author": d.get("author"),
        "text": _clean(d.get("text") or ""),
    }


def _clean(text: str) -> str:
    """Normalizza spazi e righe vuote (le pagine vecchie ne sono piene)."""
    lines = (re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in text.splitlines())
    return "\n".join(ln for ln in lines if ln)


def fetch_article(url: str) -> dict:
    """Scarica la pagina ed estrae l'articolo. Sempre un dict con 'ok'."""
    html = fetch_html(url)
    if html is None:
        return {"url": url, "ok": False, "error": "download fallito"}
    art = extract_article(html, url)
    if not art or len(art["text"]) < 200:
        return {"url": url, "ok": False, "error": "testo non estratto o troppo corto"}
    return {"url": url, "ok": True, **art}


# ------------------------------------------------------------ Wayback Machine
CDX_API = "https://web.archive.org/cdx/search/cdx"


def wayback_search(
    url_pattern: str,
    year_from: int | None = None,
    year_to: int | None = None,
    url_regex: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Cerca nell'indice CDX della Wayback Machine.

    url_pattern: prefisso, es. 'repubblica.it/2003/*', o un URL preciso.
    url_regex:   filtro sull'URL originale, es. '.*(siccit|crisi-idrica).*'
    Note: il CDX non fa ricerca full-text, solo su URL e date di cattura.
    Con url_regex usare prefissi STRETTI (sezione/anno): su un dominio intero
    il server va in timeout (504). L'Archive è spesso lento o offline: si riprova.
    """
    params = {
        "url": url_pattern,
        "output": "json",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "urlkey",  # una cattura per URL
        "limit": limit,
    }
    if year_from:
        params["from"] = str(year_from)
    if year_to:
        params["to"] = str(year_to)
    if url_regex:
        params["filter"].append(f"original:{url_regex}")
    for attempt in range(3):
        try:
            r = _session.get(CDX_API, params=params, timeout=90)
            r.raise_for_status()
            rows = r.json() if r.text.strip() else []
            break
        except (requests.RequestException, ValueError) as e:  # ValueError: pagina HTML di errore
            if attempt == 2:
                return [{"error": f"{type(e).__name__}: {e}"}]
            time.sleep(3 * (attempt + 1))
    if not rows:
        return []
    header, *data = rows
    out = []
    for row in data:
        rec = dict(zip(header, row))
        ts = rec["timestamp"]
        out.append({
            "url": rec["original"],
            "timestamp": ts,
            "capture_date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
            # 'id_' = contenuto originale senza la barra della Wayback
            "archive_url": f"https://web.archive.org/web/{ts}id_/{rec['original']}",
            "source": "wayback",
        })
    return out


def wayback_fetch(original_url: str, timestamp: str) -> dict:
    """Scarica ed estrae una cattura specifica dalla Wayback Machine."""
    res = fetch_article(f"https://web.archive.org/web/{timestamp}id_/{original_url}")
    res["url"] = original_url
    res["capture_timestamp"] = timestamp
    return res
