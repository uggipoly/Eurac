"""Estrattore: dal testo di un articolo a un JSON con gli impatti della siccità (Gemini).

Ogni impatto è una tripla settore - luogo - periodo come nel dataset Eurac, più una
frase dell'articolo (evidenza) per poter controllare a mano il risultato.
"""
from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field

from . import config


class Settore(str, Enum):
    # da allineare ai valori di impacted_sector del dataset Eurac
    agricoltura = "agricoltura"
    zootecnia = "zootecnia"
    idroelettrico_energia = "idroelettrico_energia"
    acqua_potabile = "acqua_potabile"
    industria = "industria"
    navigazione_trasporti = "navigazione_trasporti"
    turismo_ricreazione = "turismo_ricreazione"
    ecosistemi_acquatici_pesca = "ecosistemi_acquatici_pesca"
    foreste_incendi = "foreste_incendi"
    salute = "salute"
    conflitti_governance = "conflitti_governance"
    altro = "altro"


class Luogo(BaseModel):
    comune: str | None = Field(None, description="Comune (livello LAU), se citato")
    provincia: str | None = Field(None, description="Provincia (NUTS-3), se citata o deducibile")
    regione: str | None = Field(None, description="Regione (NUTS-2), se citata o deducibile")
    area_descritta: str | None = Field(
        None, description="Area non amministrativa così come scritta, es. 'bacino del Po', 'Val di Non'")


class Impatto(BaseModel):
    settore: Settore
    descrizione: str = Field(description="Impatto in una frase, in italiano")
    luogo: Luogo
    periodo: str = Field(description="Periodo dell'impatto, es. 'luglio 2003', 'estate 2022'")
    anno_inizio: int | None = Field(None, description="Anno di inizio (AAAA)")
    anno_fine: int | None = Field(None, description="Anno di fine (AAAA), uguale all'inizio se un solo anno")
    evidenza: str = Field(description="Frase copiata alla lettera dall'articolo che dimostra l'impatto")


class Estrazione(BaseModel):
    pertinente: bool = Field(description="True se l'articolo parla di siccità o scarsità d'acqua reale")
    motivo: str = Field(description="Perché è o non è pertinente, in una frase")
    hazard_country: str | None = Field(None, description="Paese della siccità, null se non pertinente")
    has_impact: bool = Field(description="True se descrive almeno un impatto concreto della siccità")
    impatti: list[Impatto] = Field(default_factory=list)


SYSTEM_PROMPT = """Stai costruendo un inventario degli impatti della siccità in Italia a partire da
articoli di giornale. Leggi l'articolo e compila il JSON richiesto.

Regole:
- "pertinente" = l'articolo parla di una siccità o scarsità d'acqua reale (meteorologica, idrologica,
  agricola). Non sono pertinenti: film, libri, metafore ("siccità di gol"), pubblicità, articoli che
  citano la parola solo di passaggio.
- Un impatto è una conseguenza concreta della siccità su persone, economia o ambiente: raccolti persi,
  razionamento dell'acqua, centrali idroelettriche ferme, morie di pesci, incendi, autobotti, ecc.
  Previsioni meteo, livelli dei fiumi senza conseguenze e richieste politiche generiche non sono impatti.
- Un impatto distinto per ogni combinazione di settore e luogo.
- Luogo: il livello più preciso citato (comune, poi provincia, poi regione). Provincia e regione si
  compilano quando si deducono con certezza dal comune (es. Cles: provincia di Trento,
  Trentino-Alto Adige). Non inventare luoghi non citati.
- Periodo: quando avviene l'impatto, non la data dell'articolo, salvo che il testo dica "oggi",
  "in questi giorni" e simili: in quel caso si usa la data dell'articolo.
- "evidenza" è una frase copiata parola per parola dal testo.
- Se l'articolo non è pertinente: has_impact = false e impatti = [].
"""

MAX_CHARS = 15000  # gli articoli più lunghi vengono troncati

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai

        key = config.get_key("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Manca GEMINI_API_KEY nel file .env")
        _client = genai.Client(api_key=key)
    return _client


def _user_message(text: str, title: str | None, date: str | None, source: str | None) -> str:
    return (
        f"Testata: {source or 'sconosciuta'}\n"
        f"Data articolo: {date or 'sconosciuta'}\n"
        f"Titolo: {title or 'sconosciuto'}\n\n"
        f"Testo:\n{text[:MAX_CHARS]}"
    )


def extract_impacts(text: str, title: str | None = None, date: str | None = None,
                    source: str | None = None, model: str | None = None) -> dict:
    """Analizza un articolo. Restituisce un dict con 'ok' e 'result' oppure 'error'."""
    from google.genai import errors, types

    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=Estrazione,  # Gemini deve rispondere con un JSON di questo schema
        temperature=0,
    )
    msg = _user_message(text, title, date, source)

    # Se un modello è sovraccarico (503) o fuori quota (429) si riprova una volta,
    # poi si passa al modello di riserva successivo.
    models = [model] if model else [config.GEMINI_MODEL, *config.GEMINI_FALLBACK_MODELS]
    resp, failures = None, []
    for m in models:
        for attempt in range(2):
            try:
                resp = _get_client().models.generate_content(model=m, contents=msg, config=cfg)
                break
            except errors.APIError as e:
                failures.append(f"{m}: {e.code}")
                if e.code in (429, 500, 503) and attempt == 0:
                    time.sleep(5)
                    continue
                break
        if resp is not None:
            model = m
            break
    if resp is None:
        return {"ok": False, "error": "nessun modello disponibile: " + ", ".join(failures)}

    try:
        result = Estrazione.model_validate_json(resp.text)
    except Exception as e:
        return {"ok": False, "error": f"JSON non valido: {e}", "raw": resp.text, "model": model}

    um = resp.usage_metadata
    return {
        "ok": True,
        "model": model,
        "result": result.model_dump(mode="json"),
        "usage": {"input_tokens": um.prompt_token_count, "output_tokens": um.candidates_token_count},
    }


def extract_from_article(article: dict, model: str | None = None) -> dict:
    """Come extract_impacts, ma prende direttamente l'output di fetch_article / wayback_fetch."""
    if not article.get("ok"):
        return {"ok": False, "error": f"articolo non disponibile: {article.get('error')}"}
    return extract_impacts(article["text"], article.get("title"), article.get("date"),
                           article.get("sitename"), model=model)
