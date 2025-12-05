# Manatal pipeline (test)

Obiettivo

- Muovere il candidato di test dalla colonna/stage origine (default: “Nuova candidatura”) allo stage destinazione (default: “Test preliminare”) e inviare un’email Gmail con template personalizzabile.

Prerequisiti

- Variabili d’ambiente:
  - `MANATAL_API_KEY` (formato header: `Token <token>`).
  - `MANATAL_JOB_DEV_ID` (ID job da processare).
  - `GMAIL_USER`, `GMAIL_APP_PASSWORD` (app password Gmail).
  - `PIPELINE_EMAIL_BODY_FILE` (path al file di testo UTF-8 con il corpo email) **oppure** `PIPELINE_EMAIL_BODY`.
  - Opzionali: `MANATAL_TEST_CANDIDATE_NAME`, `MANATAL_STAGE_FROM`, `MANATAL_STAGE_TO`, `PIPELINE_EMAIL_SUBJECT`.
- File di template: es. `emails_body/full_stack_dev_email_body.txt` con placeholder `{name}`.

Esecuzione rapida (solo candidato di test)

- Dry-run senza modifiche:  
  `python manatal_pipeline.py --dry-run`
- Esecuzione reale:  
  `python manatal_pipeline.py`

Argomenti principali

- `--job-id` (override di `MANATAL_JOB_DEV_ID`).
- `--from-stage` (default da `MANATAL_STAGE_FROM` o “Nuova candidatura”).
- `--to-stage` (default da `MANATAL_STAGE_TO` o “Test preliminare”).
- `--email-body-file` (path file corpo email; se assente, usa `PIPELINE_EMAIL_BODY`).
- `--dry-run` (nessuno spostamento, nessuna email).
- `--pause` (pausa nel processare i candidati).

Note operative

- Il filtro sui match usa stage per ID **e** nome, e scarta i match `is_active=False`.
- Se manca il corpo email (file o env), lo script termina con errore.
- Il placeholder `{name}` nel corpo della email viene sostituito con `full_name` del candidato letto da Manatal.

File utili

- Script: `manatal_pipeline.py`
- Template esempio: `emails_body/full_stack_dev_email_body.txt`
