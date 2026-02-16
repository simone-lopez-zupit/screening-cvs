import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from manatal_service import build_headers, fetch_stage_ids, fetch_job_matches, fetch_candidate, move_match


load_dotenv()


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
    # ── Easy-to-change inputs ──────────────────────────────────────────
    FROM_STAGE = "Test preliminare (TL)"
    TO_STAGE = "Colloquio tecnico (TL)"
    JOB_ID = os.getenv("MANATAL_JOB_TL_ID")
    EMAIL_SUBJECT = "Candidatura Zupit"
    EMAIL_BODY_FILE = os.getenv("SEND_TEST_EMAIL_BODY_FILE")
    GMAIL_USER = os.getenv("GMAIL_USER")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
    SLEEP_SECONDS = 33
    # ───────────────────────────────────────────────────────────────────

    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")
    if not JOB_ID:
        raise SystemExit("MANATAL_JOB_DEV_ID mancante.")

    headers = build_headers(api_key)
    stage_map = fetch_stage_ids(headers, [FROM_STAGE, TO_STAGE])
    from_stage_id = stage_map.get(FROM_STAGE)
    to_stage_id = stage_map.get(TO_STAGE)
    if from_stage_id is None or to_stage_id is None:
        raise SystemExit(f"Stage non trovati: {stage_map}")

    print(f"Cerco match in '{FROM_STAGE}' per job {JOB_ID}...")
    matches = fetch_job_matches(headers, JOB_ID, from_stage_id, stage_name=FROM_STAGE, page_size=200)
    print(f"Trovati {len(matches)} match nello stage di origine.")

    selected: List[Tuple[Dict[str, object], Dict[str, object]]] = []
    for match in matches:
        cand_id = int(match["candidate"])
        candidate = fetch_candidate(headers, cand_id)
        selected.append((match, candidate))

    print(f"Da processare: {len(selected)} candidati.")
    gmail_user = GMAIL_USER
    gmail_app_password = GMAIL_APP_PASSWORD
    body_template: Optional[str] = None
    if EMAIL_BODY_FILE:
        try:
            body_template = Path(EMAIL_BODY_FILE).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SystemExit("Corpo email mancante: imposta SEND_TEST_EMAIL_BODY_FILE.")

    for idx, (match, candidate) in enumerate(selected, start=1):
        cand_fullname = str(candidate.get("full_name") or "").strip().title()
        cand_first_name = cand_fullname.split()[0] if cand_fullname else ""

        cand_email = str(candidate.get("email") or "").strip()
        print(f"- Match {match['id']} / candidato #{idx} - {cand_fullname} ({cand_email or '!!! EMAIL MANCANTE !!!'})")

        # move_match(headers, int(match["id"]), to_stage_id)
        # print(f"  Spostato in '{TO_STAGE}'.")

        if gmail_user and gmail_app_password and cand_email:
            body = body_template.format(name=cand_first_name)
            send_gmail(gmail_user, gmail_app_password, cand_email, EMAIL_SUBJECT, body)
            print("  Email inviata.")
        else:
            print("  Email NON inviata (credenziali o email mancanti).")

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
