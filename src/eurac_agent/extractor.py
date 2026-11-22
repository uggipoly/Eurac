"""Passo 3: estrattore LLM. Articolo (testo) -> JSON validato sugli impatti della siccità.

Come funziona, in breve:
1. lo SCHEMA (classi pydantic qui sotto) descrive esattamente il JSON che vogliamo;
2. il PROMPT spiega al modello le regole (cosa è un impatto, cosa non lo è);
3. Gemini riceve schema + prompt + articolo e, con la "structured output",
   è obbligato a rispondere con un JSON conforme allo schema;
4. pydantic rivalida la risposta: se manca un campo o un valore è fuori lista, errore.

Ogni impatto è una tripla SETTORE - LUOGO - PERIODO, come nel dataset Eurac
(colonne `impacted_sector`, `NUTS`/`LAU`, `period-of-occurrence`), più una frase
di evidenza copiata dall'articolo, che serve a controllare a mano che il modello
non si sia inventato nulla.
"""
from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field

from . import config


# ------------------------------------------------------------------- schema
class Settore(str, Enum):
    """Settori impattati. Lista ispirata all'European Drought Impact Inventory;
    da allineare ai valori esatti della colonna `impacted_sector` di Eurac."""
    agricoltura = "agricoltura"
    zootecnia = "zootecnia"
    idroelettrico_energia = "idroelettrico_energia"
    acqua_potabile = "acqua_potabile"            # approvvigionamento idrico pubblico
    industria = "industria"
    navigazione_trasporti = "navigazione_trasporti"
    turismo_ricreazione = "turismo_ricreazione"
    ecosistemi_acquatici_pesca = "ecosistemi_acquatici_pesca"
    foreste_incendi = "foreste_incendi"
    salute = "salute"
    conflitti_governance = "conflitti_governance"  # razionamenti, ordinanze, liti sull'acqua
    altro = "altro"


class Luogo(BaseModel):
    comune: str | None = Field(None, description="Comune (livello LAU), se citato")
    provincia: str | None = Field(None, description="Provincia (NUTS-3), se citata o deducibile")
    regione: str | None = Field(None, description="Regione (NUTS-2), se citata o deducibile")
    area_descritta: str | None = Field(
        None, description="Area non amministrativa così come scritta: es. 'bacino del Po', 'Val di Non'")


class Impatto(BaseModel):
    settore: Settore
    descrizione: str = Field(description="Impatto in una frase, in italiano")
    luogo: Luogo
    periodo: str = Field(description="Periodo dell'impatto come scritto o deducibile, es. 'luglio 2003', 'estate 2022'")
    anno_inizio: int | None = Field(None, description="Anno in cui l'impatto inizia (AAAA)")
    anno_fine: int | None = Field(None, description="Anno in cui l'impatto finisce (AAAA), uguale a inizio se un solo anno")
    evidenza: str = Field(description="Frase copiata ALLA LETTERA dall'articolo che dimostra l'impatto")


class Estrazione(BaseModel):
    pertinente: bool = Field(description="True se l'articolo parla di siccità/scarsità d'acqua reale")
    motivo: str = Field(description="Perché è o non è pertinente, in una frase")
    hazard_country: str | None = Field(None, description="Paese della siccità (es. 'Italia'), null se non pertinente")
    has_impact: bool = Field(description="True se descrive almeno un impatto concreto della siccità")
    impatti: list[Impatto] = Field(default_factory=list)


# ------------------------------------------------------------------- prompt
SYSTEM_PROMPT = """Sei un analista che costruisce un inventario degli impatti della siccità in Italia
a partire da articoli di giornale. Leggi l'articolo e compila il JSON richiesto.

Regole:
- "pertinente" = l'articolo parla di una siccità o scarsità d'acqua REALE (meteorologica, idrologica,
  agricola). NON pertinente: film, libri, metafore ("siccità di gol"), pubblicità, articoli che citano
  la parola solo di passaggio.
- Un IMPATTO è una conseguenza concreta della siccità su persone, economia o ambiente: raccolti persi,
  razionamento dell'acqua, centrali idroelettriche ferme, morie di pesci, incendi, autobotti, ecc.
  Le sole previsioni meteo, i livelli dei fiumi senza conseguenze o le richieste politiche
  generiche NON sono impatti.
- Crea un impatto distinto per ogni combinazione diversa di settore e luogo.
- Luogo: usa il livello più preciso citato (comune > provincia > regione). Compila provincia e regione
  quando le deduci con certezza dal comune (es. Cles -> provincia di Trento, Trentino-Alto Adige).
  Non inventare luoghi non citati.
- Periodo: quello in cui l'impatto avviene, non la data dell'articolo, a meno che il testo dica
  "oggi", "in questi giorni" e simili: in quel caso usa la data dell'articolo, se fornita.
- "evidenza" deve essere una frase copiata parola per parola dal testo.
- Se l'articolo non è pertinente: has_impact = false e impatti = [].
"""

MAX_CHARS = 15000  # tagliamo articoli lunghissimi: risparmia token, l'essenziale è all'inizio


def _build_user_message(text: str, title: str | None, date: str | None, source: str | None) -> str:
    return (
        f"Testata: {source or 'sconosciuta'}\n"
        f"Data articolo: {date or 'sconosciuta'}\n"
        f"Titolo: {title or 'sconosciuto'}\n\n"
        f"Testo:\n{text[:MAX_CHARS]}"
    )


# ------------------------------------------------------------------- Gemini
_client = None


def _get_client():
    """Crea il client Gemini una volta sola (legge GEMINI_API_KEY dal .env)."""
    global _client
    if _client is None:
        from google import genai  # import qui: il resto del progetto non dipende da Gemini

        key = config.get_key("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Manca GEMINI_API_KEY nel file .env (creala su aistudio.google.com)")
        _client = genai.Client(api_key=key)
    return _client


def extract_impacts(text: str, title: str | None = None, date: str | None = None,
                    source: str | None = None, model: str | None = None) -> dict:
    """Analizza un articolo e restituisce un dict con 'ok'.

    ok=True  -> 'result' contiene l'Estrazione (come dict) e 'usage' i token usati.
    ok=False -> 'error' spiega cosa è andato storto (rete, quota, JSON non valido...).
    """
    from google.genai import errors, types

    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=Estrazione,   # <- qui passiamo lo schema pydantic
        temperature=0,                # risposte il più possibile ripetibili
    )
    msg = _build_user_message(text, title, date, source)

    # Catena di modelli: il principale, poi le riserve (vedi config.py).
    # Se un modello è sovraccarico (503) o abbiamo finito la sua quota gratuita (429),
    # lo riproviamo una volta dopo pochi secondi e poi passiamo al successivo.
    models = [model] if model else [config.GEMINI_MODEL, *config.GEMINI_FALLBACK_MODELS]
    resp, errori = None, []
    for m in models:
        for attempt in range(2):
            try:
                resp = _get_client().models.generate_content(model=m, contents=msg, config=cfg)
                break
            except errors.APIError as e:
                errori.append(f"{m}: {e.code}")
                if e.code in (429, 500, 503) and attempt == 0:
                    time.sleep(5)
                    continue
                break  # errore non temporaneo (es. 400, 404) o secondo fallimento: modello successivo
        if resp is not None:
            model = m
            break
    if resp is None:
        return {"ok": False, "error": "nessun modello disponibile: " + ", ".join(errori)}

    try:
        # rivalidazione con pydantic: garantisce tipi e valori ammessi
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
    """Comodità: prende direttamente l'output di tools.fetch_article / wayback_fetch."""
    if not article.get("ok"):
        return {"ok": False, "error": f"articolo non disponibile: {article.get('error')}"}
    return extract_impacts(article["text"], article.get("title"), article.get("date"),
                           article.get("sitename"), model=model)
