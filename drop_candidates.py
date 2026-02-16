import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from manatal_service import build_headers, fetch_stage_ids, fetch_job_matches, fetch_candidate, drop_candidate


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
        "from_stage": "Test preliminare (DEV)",
        "job_id": os.getenv("MANATAL_JOB_DEV_ID"),
        "email_subject": "Candidatura Zupit",
        "email_body_file": os.getenv("DROP_EMAIL_BODY_FILE"),
        "sleep_seconds": 65,
    },
}

# ── Change this to switch board ───────────────────────────────────
BOARD = "TL"
# ──────────────────────────────────────────────────────────────────


def send_gmail(
    user: str,
    app_password: str,
    to_email: str,
    subject: str,
    body: str,
) -> None:
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, app_password)
        smtp.send_message(msg)


def main() -> None:
    cfg = BOARDS[BOARD]
    FROM_STAGE = cfg["from_stage"]
    JOB_ID = cfg["job_id"]
    EMAIL_SUBJECT = cfg["email_subject"]
    EMAIL_BODY_FILE = cfg["email_body_file"]
    SLEEP_SECONDS = cfg["sleep_seconds"]

    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")
    if not JOB_ID:
        raise SystemExit("MANATAL_JOB_TL_ID mancante.")

    headers = build_headers(api_key)

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
    gmail_user = os.getenv("GMAIL_USER")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
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

        if gmail_user and gmail_app_password and cand_email:
            body = body_template.format(name=cand_first_name)
            send_gmail(gmail_user, gmail_app_password, cand_email, subject, body)
            print("  Email inviata.")
        else:
            print("  Email NON inviata (credenziali o email mancanti).")

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
