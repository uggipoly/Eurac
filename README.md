# Eurac agent – notizie sugli impatti della siccità

Progetto del corso **I&E Studies 2026/27 (UniTN)** sulla challenge proposta da **Eurac Research**
(gruppo Water and Human Systems): usare **agenti AI** per recuperare notizie italiane sugli impatti
della siccità, soprattutto quelle **storiche (2000–2021)** che la pipeline di Eurac basata su
Google News non riesce a trovare.

Ogni impatto viene descritto come tripla **settore – luogo – periodo**, allineata al dataset
annotato di Eurac.

## Stato

| Passo | Contenuto | Stato |
|---|---|---|
| 1 | Setup (venv, dipendenze, `.env`) | fatto |
| 2 | Strumenti: ricerca web, estrazione testo, Wayback Machine | fatto |
| 3 | Estrattore LLM (articolo → JSON validato) | da fare |
| 4 | Agente iterativo (query → ricerca → lettura → nuove query) | da fare |
| 5 | Valutazione sul 2022 (recall / precisione vs dataset Eurac) | da fare |
| 6 | Confronto configurazioni (query fisse / agente / agente + validatore) | da fare |


## Installazione

Serve Python 3.10 o più recente.

```bash
git clone https://github.com/uggipoly/Eurac.git
cd Eurac
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # poi inserisci le tue chiavi API in .env
python check_setup.py              # verifica che tutto sia a posto
```

> `.env` contiene le chiavi API personali: **non va mai committato** (è già nel `.gitignore`).

## Uso

```bash
python demo_tools.py                                   # demo completa
python demo_tools.py search "siccità Trentino 2022"    # ricerca web (DuckDuckGo)
python demo_tools.py fetch URL                         # scarica ed estrae un articolo
python demo_tools.py wayback "repubblica.it/2003/*" 2003 2007 ".*siccit.*"   # Wayback Machine
```

## Struttura

```
src/eurac_agent/
  config.py     lettura di .env e percorsi del progetto
  tools.py      search_web, search_news, fetch_article, wayback_search, wayback_fetch
check_setup.py  verifica dell'ambiente
demo_tools.py   prova a riga di comando degli strumenti
data/, logs/    creati in locale, non versionati
```

## Note sugli strumenti

- **DuckDuckGo** (`ddgs`) non richiede chiavi ma non filtra per intervalli di anni (solo
  giorno/settimana/mese/anno).
- **Wayback Machine (CDX API)** cerca solo su URL e date di cattura, non sul testo. Con un filtro
  regex servono prefissi stretti (es. `repubblica.it/2003/g/sezioni/cronaca/*`), altrimenti il
  server risponde 504. L'Internet Archive è spesso lento: le richieste vengono ripetute.
