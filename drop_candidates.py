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
    # ── Board configurations ──────────────────────────────────────────
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
