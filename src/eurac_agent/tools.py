"""Strumenti di ricerca: DuckDuckGo, download ed estrazione del testo, Wayback Machine."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse

import requests
import trafilatura
from ddgs import DDGS

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) eurac-drought-research/0.1"
TIMEOUT = 20
MIN_TEXT_CHARS = 200  # sotto questa lunghezza non consideriamo il testo un articolo
CDX_API = "https://web.archive.org/cdx/search/cdx"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})

# Pagine da scartare: social e siti video, fotogallery, file che non sono HTML.
# I PDF sono esclusi perché trafilatura non li legge.
NON_TEXT_DOMAINS = (
    "facebook.com", "instagram.com", "youtube.com", "youtu.be", "tiktok.com",
    "twitter.com", "x.com", "pinterest.", "flickr.com", "linkedin.com",
    "vimeo.com", "dailymotion.com", "threads.net",
)
NON_TEXT_PATH = re.compile(
    r"(galleri|gallery|fotogaller|/foto/|/fotos?/|/photos?/|/video/|/videos/|/reel/|/tv/|/podcast)",
    re.IGNORECASE,
)
NON_TEXT_EXT = re.compile(r"\.(jpe?g|png|gif|webp|svg|mp4|mov|avi|mp3|wav|pdf|zip)$", re.IGNORECASE)


def is_text_url(url: str | None) -> bool:
    """True se l'URL sembra un articolo di testo."""
    if not url:
        return False
    p = urlparse(url)
    if any(d in p.netloc.lower() for d in NON_TEXT_DOMAINS):
        return False
    return not (NON_TEXT_PATH.search(p.path) or NON_TEXT_EXT.search(p.path))


def url_year(url: str) -> int | None:
    """Anno presente nell'URL (es. /2003/), se c'è."""
    m = re.search(r"(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)", urlparse(url).path)
    return int(m.group(1)) if m else None


# DuckDuckGo accetta come timelimit solo 'd', 'w', 'm', 'y' (non un intervallo di anni):
# per gli anni vecchi si mette l'anno nella query e si usa la Wayback Machine.
def search_web(query: str, max_results: int = 10, timelimit: str | None = None) -> list[dict]:
    """Ricerca web DuckDuckGo (regione Italia), solo pagine di testo."""
    try:
        # il doppio dei risultati, perché una parte viene scartata dal filtro
        raw = DDGS().text(query, region="it-it", max_results=max_results * 2, timelimit=timelimit)
    except Exception as e:  # ddgs solleva eccezioni anche quando non trova nulla
        return [{"error": f"{type(e).__name__}: {e}", "query": query}]
    out = [
        {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body"),
         "url_year": url_year(r.get("href") or ""), "source": "ddg_web"}
        for r in raw if is_text_url(r.get("href"))
    ]
    return out[:max_results]


def search_news(query: str, max_results: int = 10, timelimit: str | None = None) -> list[dict]:
    """Ricerca DuckDuckGo News (notizie recenti, con data e testata)."""
    try:
        raw = DDGS().news(query, region="it-it", max_results=max_results * 2, timelimit=timelimit)
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}", "query": query}]
    out = [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("body"),
            "date": r.get("date"),
            "publisher": r.get("source"),
            "source": "ddg_news",
        }
        for r in raw if is_text_url(r.get("url"))
    ]
    return out[:max_results]


def fetch_html(url: str) -> str | None:
    try:
        r = _session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException:
        return None
    # senza charset nell'header requests usa ISO-8859-1 e le accentate si rompono
    if "charset" not in r.headers.get("Content-Type", "").lower():
        r.encoding = r.apparent_encoding
    return r.text


def _trafilatura(html: str, url: str | None, precision: bool) -> dict | None:
    out = trafilatura.extract(
        html, url=url, output_format="json", with_metadata=True,
        include_comments=False, include_tables=False,
        favor_precision=precision, favor_recall=not precision,
    )
    return json.loads(out) if out else None


def extract_article(html: str, url: str | None = None) -> dict | None:
    """Estrae titolo, data, testata e testo con trafilatura.

    Se in modalità precisa il testo è troppo corto (succede con le pagine vecchie)
    si riprova in modalità recall.
    """
    d = _trafilatura(html, url, precision=True)
    if not d or len(d.get("text") or "") < MIN_TEXT_CHARS:
        d = _trafilatura(html, url, precision=False) or d
    if not d:
        return None
    return {
        "title": d.get("title"),
        "date": d.get("date"),
        "sitename": d.get("sitename") or d.get("hostname"),
        "author": d.get("author"),
        "text": _clean(d.get("text") or ""),
    }


def _clean(text: str) -> str:
    """Toglie spazi doppi e righe vuote."""
    lines = (re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines())
    return "\n".join(ln for ln in lines if ln)


def fetch_article(url: str) -> dict:
    """Scarica la pagina ed estrae l'articolo. Restituisce sempre un dict con 'ok'."""
    if not is_text_url(url):
        return {"url": url, "ok": False, "error": "non è una pagina di testo"}
    html = fetch_html(url)
    if html is None:
        return {"url": url, "ok": False, "error": "download fallito"}
    art = extract_article(html, url)
    if not art or len(art["text"]) < MIN_TEXT_CHARS:
        return {"url": url, "ok": False, "error": "testo non estratto o troppo corto"}
    return {"url": url, "ok": True, **art}


def wayback_search(
    url_pattern: str,
    year_from: int | None = None,
    year_to: int | None = None,
    url_regex: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Cerca nell'indice CDX della Wayback Machine (solo URL e date, non il testo).

    url_pattern: prefisso, es. 'repubblica.it/2003/g/sezioni/cronaca/*'
    url_regex:   filtro sull'URL, es. '.*siccit.*'
    Con url_regex il prefisso deve essere stretto, su un dominio intero il server dà 504.
    """
    params = {
        "url": url_pattern,
        "output": "json",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "urlkey",  # una sola cattura per URL
        "limit": limit * 3,    # margine per le pagine scartate da is_text_url
    }
    if year_from:
        params["from"] = str(year_from)
    if year_to:
        params["to"] = str(year_to)
    if url_regex:
        params["filter"].append(f"original:{url_regex}")

    for attempt in range(3):  # l'Archive è spesso lento, si riprova
        try:
            r = _session.get(CDX_API, params=params, timeout=90)
            r.raise_for_status()
            rows = r.json() if r.text.strip() else []
            break
        except (requests.RequestException, ValueError) as e:  # ValueError: pagina di errore HTML
            if attempt == 2:
                return [{"error": f"{type(e).__name__}: {e}"}]
            time.sleep(3 * (attempt + 1))
    if not rows:
        return []

    header, *data = rows
    out = []
    for row in data:
        rec = dict(zip(header, row))
        if not is_text_url(rec["original"]):
            continue
        ts = rec["timestamp"]
        out.append({
            "url": rec["original"],
            "timestamp": ts,
            "capture_date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
            # con 'id_' la Wayback restituisce la pagina originale senza la sua barra
            "archive_url": f"https://web.archive.org/web/{ts}id_/{rec['original']}",
            "source": "wayback",
        })
    return out[:limit]


def wayback_fetch(original_url: str, timestamp: str) -> dict:
    """Scarica ed estrae una cattura della Wayback Machine."""
    res = fetch_article(f"https://web.archive.org/web/{timestamp}id_/{original_url}")
    res["url"] = original_url
    res["capture_timestamp"] = timestamp
    if res.get("ok") and res.get("sitename") in (None, "archive.org", "web.archive.org"):
        res["sitename"] = urlparse(original_url).hostname
    return res
