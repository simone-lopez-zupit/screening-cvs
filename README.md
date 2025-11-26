Project overview

- Estrae info dai PDF dei CV con GPT-4o, genera un Excel colorato e due zip dei CV accettati e rifiutati.
- Deduplica i PDF per hash: i duplicati vengono spostati in una cartella a parte prima del parsing.

Prerequisiti

- Python 3.10+ consigliato.
- Variabile ambiente OPENAI_API_KEY impostata con la tua chiave OpenAI.
- Puoi copiare `.env.example` in `.env` e valorizzare `OPENAI_API_KEY`, poi eseguire `export $(grep -v '^#' .env | xargs)` oppure `source .env` prima di lanciare lo script.

Setup

- (opzionale) python -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt

Esecuzione

- Comando base: python process_cvs.py --input-dir cvs
- Opzioni utili:
  - --duplicates-dir cvs_duplicati cartella dove spostare i PDF duplicati (default)
  - --model gpt-4o-mini se vuoi cambiare modello (default: gpt-4o)
  - --pause 0.5 pausa in secondi tra chiamate API
  - --limit 10 limita il numero di PDF da processare

Output

- Deduplica: eventuali duplicati vengono spostati in <duplicates-dir>.
- Excel: cv_YYYYMMDD_HHMMSS.xlsx con righe verdi (ACCETTATO) o rosse (RIFIUTATO) e tutti i campi estratti/condizioni.
- Zip: cv_approvati_YYYYMMDD_HHMMSS.zip con i PDF accettati; cv_rifiutati_YYYYMMDD_HHMMSS.zip con i PDF rifiutati.
