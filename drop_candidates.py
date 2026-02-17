import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from services.gmail_service import send_gmail
from services.manatal_service import build_headers, fetch_stage_ids, fetch_job_matches, fetch_candidate, drop_candidate

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
BOARDS = {
    "TL": {
        "from_stage": "Nuova candidatura (TL)",
        "job_id": os.getenv("MANATAL_JOB_TL_ID"),
        "email_subject": "Candidatura Zupit",
        "email_body_file": os.getenv("DROP_EMAIL_BODY_FILE"),
        "sleep_seconds": 65,
    },
    "DEV": {
        "from_stage": "Test preliminare",
        "job_id": os.getenv("MANATAL_JOB_DEV_ID"),
        "email_subject": "Candidatura Zupit",
        "email_body_file": os.getenv("DROP_EMAIL_BODY_FILE"),
        "sleep_seconds": 65,
    },
}

GMAIL_USER         = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# ── Change this to switch board ───────────────────────────────────
BOARD = "DEV"
# ──────────────────────────────────────────────────────────────────


def main() -> None:
    cfg = BOARDS[BOARD]
    FROM_STAGE = cfg["from_stage"]
    JOB_ID = cfg["job_id"]
    EMAIL_SUBJECT = cfg["email_subject"]
    EMAIL_BODY_FILE = cfg["email_body_file"]
    SLEEP_SECONDS = cfg["sleep_seconds"]

    headers = build_headers()

    stage_map = fetch_stage_ids(headers, [FROM_STAGE])
    from_stage_id = stage_map.get(FROM_STAGE)
    if from_stage_id is None:
        raise SystemExit(f"Stage non trovato: '{FROM_STAGE}'")

    print(f"Cerco match in '{FROM_STAGE}' per job {JOB_ID}...")
    matches = fetch_job_matches(headers, JOB_ID, from_stage_id, stage_name=FROM_STAGE, page_size=200)
    print(f"Trovati {len(matches)} match nello stage '{FROM_STAGE}'.")

    selected: List[Tuple[Dict[str, object], Dict[str, object]]] = []
    for match in matches:
        cand_id = int(match["candidate"])
        candidate = fetch_candidate(headers, cand_id)
        selected.append((match, candidate))

    print(f"Da processare: {len(selected)} candidati.")
    subject = EMAIL_SUBJECT
    body_template_path = EMAIL_BODY_FILE
    body_template: Optional[str] = None
    if body_template_path:
        try:
            body_template = Path(body_template_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SystemExit("Corpo email mancante: passa --email-body-file o imposta DROP_EMAIL_BODY_FILE.")

    for idx, (match, candidate) in enumerate(selected, start=1):
        cand_fullname = str(candidate.get("full_name") or "").strip().title()
        cand_first_name = cand_fullname.split()[0] if cand_fullname else ""

        cand_email = str(candidate.get("email") or "").strip()
        print(f"- Match {match['id']} / candidato #{idx} - {cand_fullname} ({cand_email or '!!! EMAIL MANCANTE !!!'})")

        drop_candidate(headers, int(match["id"]))
        print("  Droppato.")

        if GMAIL_USER and GMAIL_APP_PASSWORD and cand_email:
            body = body_template.format(name=cand_first_name)
            send_gmail(GMAIL_USER, GMAIL_APP_PASSWORD, cand_email, subject, body)
            print("  Email inviata.")
        else:
            print("  Email NON inviata (credenziali o email mancanti).")

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
