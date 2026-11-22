# Eurac agent – notizie sugli impatti della siccità

Progetto del corso I&E Studies 2026/27 (UniTN) per la challenge di Eurac Research
(gruppo Water and Human Systems). L'obiettivo è recuperare notizie italiane sugli impatti della
siccità, soprattutto quelle storiche (2000–2021) che la pipeline di Eurac basata su Google News
non riesce a trovare, usando un agente che cerca sul web e un modello linguistico che legge gli articoli.

Ogni impatto viene descritto come tripla settore – luogo – periodo, come nel dataset annotato di Eurac.

## Stato

| Passo | Contenuto | Stato |
|---|---|---|
| 1 | Setup (venv, dipendenze, `.env`) | fatto |
| 2 | Strumenti: ricerca web, estrazione testo, Wayback Machine | fatto |
| 3 | Estrattore (articolo -> JSON con gli impatti, con Gemini) | fatto |
| 4 | Agente iterativo (query -> ricerca -> lettura -> nuove query) | da fare |
| 5 | Valutazione sul 2022 (recall e precisione rispetto al dataset Eurac) | da fare |
| 6 | Confronto configurazioni (query fisse / agente / agente + validatore) | da fare |

## Installazione

Serve Python 3.10 o più recente.

```bash
git clone https://github.com/uggipoly/Eurac.git
cd Eurac
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python check_setup.py
```

Nel file `.env` va messa la chiave di Gemini (`GEMINI_API_KEY`). Si crea gratis su
https://aistudio.google.com/apikey: conviene crearla in un progetto Google Cloud nuovo e senza
fatturazione attiva, così resta sul piano gratuito. `.env` non va mai committato (è nel `.gitignore`).

## Uso

```bash
python demo_tools.py                                   # prova degli strumenti
python demo_tools.py search "siccità Trentino 2022"    # ricerca web (DuckDuckGo)
python demo_tools.py fetch URL                         # scarica ed estrae un articolo
python demo_tools.py wayback "repubblica.it/2003/g/sezioni/cronaca/*" 2003 2003 ".*siccit.*"

python demo_extract.py                                 # estrattore su 3 articoli di prova
python demo_extract.py URL                             # estrattore su un articolo qualsiasi
python demo_extract.py wayback URL TIMESTAMP           # estrattore su una pagina della Wayback
```

Le estrazioni vengono salvate anche in `logs/estrazioni.jsonl`.

## Struttura

```
src/eurac_agent/
  config.py       lettura di .env e percorsi
  tools.py        search_web, search_news, fetch_article, wayback_search, wayback_fetch
  extractor.py    schema degli impatti, prompt e chiamata a Gemini
check_setup.py    verifica dell'ambiente
demo_tools.py     prova degli strumenti da riga di comando
demo_extract.py   prova dell'estrattore
data/, logs/      creati in locale, non versionati
```

## Note

- DuckDuckGo non filtra per intervalli di anni (solo ultimo giorno/settimana/mese/anno) e restituisce
  soprattutto pagine recenti. Per il 2000–2021 si usa la Wayback Machine.
- La Wayback Machine (CDX API) cerca solo su URL e date di cattura, non sul testo. Con un filtro
  regex servono prefissi stretti (es. `repubblica.it/2003/g/sezioni/cronaca/*`), altrimenti il
  server risponde 504. L'Internet Archive è spesso lento: le richieste vengono ripetute.
- Vengono scartati social, video, fotogallery e PDF.
- Modelli Gemini: principale `gemini-3.5-flash`, riserva `gemini-3.5-flash-lite`; si cambiano nel `.env`
  con `GEMINI_MODEL` e `GEMINI_FALLBACK_MODELS`.
