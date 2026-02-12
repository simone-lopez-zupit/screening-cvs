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

    url: Optional[str] = f"{API_BASE}/match-stages/?page_size=200"
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
    return matches[:20]


def fetch_candidate(headers: Dict[str, str], candidate_id: int) -> Dict[str, object]:
    resp = requests.get(f"{API_BASE}/candidates/{candidate_id}/", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def drop_candidate(headers: Dict[str, str], match_id: int) -> None:
    payload = {"is_active": "false"}
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
    parser = argparse.ArgumentParser(description="Pipeline di test Manatal -> drop candidate + email Gmail.")
    parser.add_argument("--job-id", help="ID del job Manatal (fallback: MANATAL_JOB_TL_ID).")

    parser.add_argument(
        "--email-subject",
        default=os.getenv("PIPELINE_EMAIL_SUBJECT", "Candidatura Zupit"),
        help="Oggetto dell'email da inviare.",
    )
    parser.add_argument(
        "--email-body-file",
        default=os.getenv("DROP_EMAIL_BODY_FILE"),
        help="Percorso del file di testo per il corpo email (UTF-8). Se non impostato, usa env DROP_EMAIL_BODY_FILE.",
    )
    args = parser.parse_args()

    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")
    job_id = args.job_id or os.getenv("MANATAL_JOB_TL_ID")
    if not job_id:
        raise SystemExit("MANATAL_JOB_TL_ID mancante.")

    headers = build_headers(api_key)

    from_stage = "Nuova candidatura (TL)"
    stage_map = fetch_stage_ids(headers, [from_stage])
    from_stage_id = stage_map.get(from_stage)
    if from_stage_id is None:
        raise SystemExit(f"Stage non trovato: '{from_stage}'")

    print(f"Cerco match in '{from_stage}' per job {job_id}...")
    matches = fetch_job_matches(headers, job_id, from_stage_id, stage_name=from_stage, page_size=200)
    print(f"Trovati {len(matches)} match nello stage '{from_stage}'.")

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

        time.sleep(65)


if __name__ == "__main__":
    main()
