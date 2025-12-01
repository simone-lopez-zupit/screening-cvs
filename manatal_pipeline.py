import argparse
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
import time
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from dotenv import load_dotenv


load_dotenv()

API_BASE = "https://api.manatal.com/open/v3"


def build_headers(raw_token: str) -> Dict[str, str]:
    token = raw_token.strip()
    if not token.lower().startswith("token "):
        token = f"Token {token}"
    return {"Authorization": token, "Content-Type": "application/json"}


def absolute_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("http"):
        return url
    return f"{API_BASE.rstrip('/')}/{url.lstrip('/')}"


def fetch_stage_ids(headers: Dict[str, str], stage_names: Iterable[str]) -> Dict[str, int]:
    wanted = {name.lower(): name for name in stage_names}
    found: Dict[str, int] = {}

    url: Optional[str] = f"{API_BASE}/match-stages/"
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for stage in data.get("results", []):
            name = str(stage.get("name") or "")
            key = name.lower()
            if key in wanted and wanted[key] not in found:
                found[wanted[key]] = int(stage["id"])
        url = absolute_url(data.get("next"))

    return found


def fetch_job_matches(
    headers: Dict[str, str],
    job_id: str,
    stage_id: int,
    stage_name: Optional[str] = None,
    page_size: int = 100,
    only_active: bool = True,
) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    url: Optional[str] = f"{API_BASE}/jobs/{job_id}/matches/?page_size={page_size}"
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for match in data.get("results", []):
            stage = match.get("stage") or {}
            if int(stage.get("id", -1)) != stage_id:
                continue
            if stage_name and str(stage.get("name") or "").strip().lower() != stage_name.strip().lower():
                continue
            if only_active and not match.get("is_active", False):
                continue
            matches.append(match)
        url = absolute_url(data.get("next"))
    return matches


def fetch_candidate(headers: Dict[str, str], candidate_id: int) -> Dict[str, object]:
    resp = requests.get(f"{API_BASE}/candidates/{candidate_id}/", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def move_match(headers: Dict[str, str], match_id: int, stage_id: int) -> None:
    payload = {"stage": {"id": stage_id}}
    resp = requests.patch(
        f"{API_BASE}/matches/{match_id}/",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


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
    parser.add_argument("--job-id", help="ID del job Manatal (fallback: MANATAL_JOB_ID).")

    parser.add_argument(
        "--from-stage",
        default=os.getenv("MANATAL_STAGE_FROM", "Nuova candidatura"),
        help='Nome dello stage di origine (default: "Nuova candidatura").',
    )
    parser.add_argument(
        "--to-stage",
        default=os.getenv("MANATAL_STAGE_TO", "Test preliminare"),
        help='Nome dello stage di destinazione (default: "Test preliminare").',
    )
    parser.add_argument(
        "--email-subject",
        default=os.getenv("PIPELINE_EMAIL_SUBJECT", "Step successivo: test preliminare"),
        help="Oggetto dell'email da inviare.",
    )
    parser.add_argument(
        "--email-body-file",
        default=os.getenv("PIPELINE_EMAIL_BODY_FILE"),
        help="Percorso del file di testo per il corpo email (UTF-8). Se non impostato, usa env PIPELINE_EMAIL_BODY.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Non spostare né inviare email; stampa solo cosa farebbe.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.0,
        help="Secondi di pausa tra un candidato e il successivo (default: 0).",
    )
    args = parser.parse_args()

    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")
    job_id = args.job_id or os.getenv("MANATAL_JOB_ID")
    if not job_id:
        raise SystemExit("MANATAL_JOB_ID mancante.")

    headers = build_headers(api_key)
    stage_map = fetch_stage_ids(headers, [args.from_stage, args.to_stage])
    from_stage_id = stage_map.get(args.from_stage)
    to_stage_id = stage_map.get(args.to_stage)
    if from_stage_id is None or to_stage_id is None:
        raise SystemExit(f"Stage non trovati: {stage_map}")

    print(f"Cerco match in '{args.from_stage}' per job {job_id}...")
    matches = fetch_job_matches(headers, job_id, from_stage_id, stage_name=args.from_stage,page_size=800)
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
    body_template_path = args.email_body_file
    body_template: Optional[str] = None
    if body_template_path:
        try:
            body_template = Path(body_template_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SystemExit("Corpo email mancante: passa --email-body-file o imposta PIPELINE_EMAIL_BODY_FILE.")

    for idx, (match, candidate) in enumerate(selected, start=1):
        cand_name = str(candidate.get("full_name") or "").strip()
        cand_email = str(candidate.get("email") or "").strip()
        print(f"- Match {match['id']} / candidato {cand_name} ({cand_email or 'email mancante'})")

        if args.dry_run:
            print("  DRY-RUN: salto move+email. Per il seguente candidato:")
            print("cand email: " + cand_email)
            print("cand name: " + cand_name)
            continue

        move_match(headers, int(match["id"]), to_stage_id)
        print(f"  Spostato in '{args.to_stage}'.")

        if gmail_user and gmail_app_password and cand_email:
            body = body_template.format(name=cand_name)
            send_gmail(gmail_user, gmail_app_password, cand_email, subject, body)
            print("  Email inviata.")
        else:
            print("  Email NON inviata (credenziali o email mancanti).")

        if args.pause > 0 and idx < len(selected):
            time.sleep(args.pause)


if __name__ == "__main__":
    main()
