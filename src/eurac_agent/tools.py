"""Strumenti dell'agente: ricerca web, download+estrazione testo, Wayback Machine.

Ogni funzione restituisce dati semplici (dict/list) così l'agente e i log JSONL
possono usarli direttamente.
"""
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

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


# ------------------------------------------------- filtro: solo pagine di testo
# Siti social/video: il testo è dietro login o è solo una didascalia.
NON_TEXT_DOMAINS = (
    "facebook.com", "instagram.com", "youtube.com", "youtu.be", "tiktok.com",
    "twitter.com", "x.com", "pinterest.", "flickr.com", "linkedin.com",
    "vimeo.com", "dailymotion.com", "threads.net",
)
# Pezzi di URL tipici di fotogallery e video (es. repubblica.it/2003/e/gallerie/...).
NON_TEXT_PATH = re.compile(
    r"(galleri|gallery|fotogaller|/foto/|/fotos?/|/photos?/|/video/|/videos/|/reel/|/tv/|/podcast)",
    re.IGNORECASE,
)
# File che non sono pagine HTML (immagini, video, audio). I PDF li teniamo fuori per ora:
# trafilatura non li legge (le emeroteche in PDF andranno gestite a parte).
NON_TEXT_EXT = re.compile(r"\.(jpe?g|png|gif|webp|svg|mp4|mov|avi|mp3|wav|pdf|zip)$", re.IGNORECASE)


def is_text_url(url: str | None) -> bool:
    """True se l'URL sembra un articolo di testo (non social, foto, video o file)."""
    if not url:
        return False
    p = urlparse(url)
    host = p.netloc.lower()
    if any(d in host for d in NON_TEXT_DOMAINS):
        return False
    return not (NON_TEXT_PATH.search(p.path) or NON_TEXT_EXT.search(p.path))


def url_year(url: str) -> int | None:
    """Anno scritto nell'URL, se c'è (molti giornali usano /2003/ o -2003-).

    Serve perché DuckDuckGo NON filtra per anno: la data vera la sapremo solo
    dopo aver scaricato l'articolo, ma l'URL spesso la anticipa.
    """
    m = re.search(r"(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)", urlparse(url).path)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- ricerca web
# Nota sugli anni: DDG accetta solo timelimit 'd','w','m','y' (ultimo giorno/settimana/...).
# Con None non c'è limite, ma in pratica restituisce soprattutto pagine recenti.
# Per il 2000-2021 conviene: anno nella query + filtro url_year + Wayback Machine.
def search_web(query: str, max_results: int = 10, timelimit: str | None = None) -> list[dict]:
    """Ricerca DuckDuckGo (risultati web, regione Italia), solo pagine di testo."""
    try:
        # chiediamo il doppio dei risultati perché una parte verrà scartata dal filtro
        raw = DDGS().text(query, region="it-it", max_results=max_results * 2, timelimit=timelimit)
    except Exception as e:  # ddgs solleva eccezioni per rate limit / nessun risultato
        return [{"error": f"{type(e).__name__}: {e}", "query": query}]
    out = [
        {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body"),
         "url_year": url_year(r.get("href") or ""), "source": "ddg_web"}
        for r in raw if is_text_url(r.get("href"))
    ]
    return out[:max_results]


def search_news(query: str, max_results: int = 10, timelimit: str | None = None) -> list[dict]:
    """Ricerca DuckDuckGo News (soprattutto notizie recenti, con data e testata)."""
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


# ------------------------------------------------------- download + estrazione
def fetch_html(url: str) -> str | None:
    try:
        r = _session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException:
        return None
    # Se il server non dichiara il charset, requests assume ISO-8859-1 e le lettere
    # accentate di una pagina UTF-8 diventano "Ã ": in quel caso lo indoviniamo dal contenuto.
    if "charset" not in r.headers.get("Content-Type", "").lower():
        r.encoding = r.apparent_encoding
    return r.text


MIN_TEXT_CHARS = 200  # sotto questa soglia non è un articolo (menu, didascalia, paywall)


def _trafilatura(html: str, url: str | None, precision: bool) -> dict | None:
    out = trafilatura.extract(
        html, url=url, output_format="json", with_metadata=True,
        include_comments=False, include_tables=False,
        favor_precision=precision, favor_recall=not precision,
    )
    return json.loads(out) if out else None


def extract_article(html: str, url: str | None = None) -> dict | None:
    """Estrae titolo, data, testata e testo principale con trafilatura.

    1° tentativo "preciso" (scarta menu e box laterali); se il testo viene
    troppo corto (capita con le pagine vecchie, impaginate a tabelle) riprova
    in modalità "recall", che tiene più testo.
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
    """Normalizza spazi e righe vuote (le pagine vecchie ne sono piene)."""
    lines = (re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in text.splitlines())
    return "\n".join(ln for ln in lines if ln)


def fetch_article(url: str) -> dict:
    """Scarica la pagina ed estrae l'articolo. Sempre un dict con 'ok'."""
    if not is_text_url(url):
        return {"url": url, "ok": False, "error": "non è una pagina di testo (social/foto/video/file)"}
    html = fetch_html(url)
    if html is None:
        return {"url": url, "ok": False, "error": "download fallito"}
    art = extract_article(html, url)
    if not art or len(art["text"]) < MIN_TEXT_CHARS:
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
    Fotogallery e video vengono scartati qui in Python (con un filtro negativo
    lato server il CDX va in 504), per questo chiediamo 3x risultati.
    """
    params = {
        "url": url_pattern,
        "output": "json",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "urlkey",  # una cattura per URL
        "limit": limit * 3,
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
        if not is_text_url(rec["original"]):
            continue
        ts = rec["timestamp"]
        out.append({
            "url": rec["original"],
            "timestamp": ts,
            "capture_date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
            # 'id_' = contenuto originale senza la barra della Wayback
            "archive_url": f"https://web.archive.org/web/{ts}id_/{rec['original']}",
            "source": "wayback",
        })
    return out[:limit]


def wayback_fetch(original_url: str, timestamp: str) -> dict:
    """Scarica ed estrae una cattura specifica dalla Wayback Machine."""
    res = fetch_article(f"https://web.archive.org/web/{timestamp}id_/{original_url}")
    res["url"] = original_url
    res["capture_timestamp"] = timestamp
    # trafilatura vedrebbe "archive.org" come testata: usiamo il sito originale
    if res.get("ok") and res.get("sitename") in (None, "archive.org", "web.archive.org"):
        res["sitename"] = urlparse(original_url).hostname
    return res
