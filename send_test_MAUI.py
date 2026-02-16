import argparse
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from manatal_service import build_headers, fetch_stage_ids, fetch_job_matches, fetch_candidate, move_match


load_dotenv()

# ── Configuration (defaults, overridable via CLI args) ────────────────
DEFAULT_FROM_STAGE       = os.getenv("MANATAL_STAGE_FROM", "Nuova candidatura")
DEFAULT_TO_STAGE         = os.getenv("MANATAL_STAGE_TO", "Test preliminare")
DEFAULT_EMAIL_SUBJECT    = os.getenv("PIPELINE_EMAIL_SUBJECT", "Candidatura Zupit")
DEFAULT_EMAIL_BODY_FILE  = os.getenv("SEND_TEST_EMAIL_MAUI_BODY_FILE")
SLEEP_SECONDS            = 78
# ──────────────────────────────────────────────────────────────────────


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
    parser = argparse.ArgumentParser(description="Pipeline di test Manatal -> stage + email Gmail.")
    parser.add_argument("--job-id", help="ID del job Manatal (fallback: MANATAL_JOB_DEV_ID).")

    parser.add_argument(
        "--from-stage",
        default=DEFAULT_FROM_STAGE,
        help='Nome dello stage di origine (default: "Nuova candidatura").',
    )
    parser.add_argument(
        "--to-stage",
        default=DEFAULT_TO_STAGE,
        help='Nome dello stage di destinazione (default: "Test preliminare").',
    )
    parser.add_argument(
        "--email-subject",
        default=DEFAULT_EMAIL_SUBJECT,
        help="Oggetto dell'email da inviare.",
    )
    parser.add_argument(
        "--email-maui-body-file",
        default=DEFAULT_EMAIL_BODY_FILE,
        help="Percorso del file di testo per il corpo email (UTF-8). Se non impostato, usa env SEND_TEST_EMAIL_MAUI_BODY_FILE.",
    )
    args = parser.parse_args()

    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")
    job_id = args.job_id or os.getenv("MANATAL_JOB_MAUI_ID")
    if not job_id:
        raise SystemExit("MANATAL_JOB_MAUI_ID mancante.")

    headers = build_headers(api_key)
    stage_map = fetch_stage_ids(headers, [args.from_stage, args.to_stage])
    from_stage_id = stage_map.get(args.from_stage)
    to_stage_id = stage_map.get(args.to_stage)
    if from_stage_id is None or to_stage_id is None:
        raise SystemExit(f"Stage non trovati: {stage_map}")

    print(f"Cerco match in '{args.from_stage}' per job {job_id}...")
    matches = fetch_job_matches(headers, job_id, from_stage_id, stage_name=args.from_stage, page_size=200)
    print(f"Trovati {len(matches)} match nello stage di origine.")

    selected: List[Tuple[Dict[str, object], Dict[str, object]]] = []
    for match in matches:
        cand_id = int(match["candidate"])
        candidate = fetch_candidate(headers, cand_id)
        selected.append((match, candidate))

    print(f"Da processare: {len(selected)} candidati.")
    gmail_user = os.getenv("GMAIL_USER")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
    subject = args.email_subject
    body_template_path = args.email_maui_body_file
    body_template: Optional[str] = None
    if body_template_path:
        try:
            body_template = Path(body_template_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SystemExit("Corpo email mancante: passa --email-maui-body-file o imposta PIPELINE_EMAIL_MAUI_BODY_FILE.")

    for idx, (match, candidate) in enumerate(selected, start=1):
        cand_fullname = str(candidate.get("full_name") or "").strip().title()
        cand_first_name = cand_fullname.split()[0] if cand_fullname else ""

        cand_email = str(candidate.get("email") or "").strip()
        print(f"- Match {match['id']} / candidato #{idx} - {cand_fullname} ({cand_email or '!!! EMAIL MANCANTE !!!'})")

        move_match(headers, int(match["id"]), to_stage_id)
        print(f"  Spostato in '{args.to_stage}'.")

        if gmail_user and gmail_app_password and cand_email:
            body = body_template.format(name=cand_first_name)
            send_gmail(gmail_user, gmail_app_password, cand_email, subject, body)
            print("  Email inviata.")
        else:
            print("  Email NON inviata (credenziali o email mancanti).")

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
