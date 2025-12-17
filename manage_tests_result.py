import argparse
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
import time
from pathlib import Path

import pandas as pd
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
        time.sleep(5)

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


def drop_candidate(headers: Dict[str, str], match_id: int) -> None:
    payload = {"is_active": "false"}
    resp = requests.patch(
        f"{API_BASE}/matches/{match_id}/",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


def has_testdome_note(match_pk: int, headers: Dict[str, str]) -> bool:
    url = f"{API_BASE}/matches/{match_pk}/notes/"

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    notes = resp.json()

    return any(
        isinstance(note.get("text"), str) and "testdome" in note["text"].lower()
        for note in notes
    )


def format_excel(input_path: str):
    df = pd.read_excel(input_path, sheet_name="All candidates", skiprows=3)

    df['score'] = (
        df['Total\nScore']
        .astype(str)
        .str.replace('%', '', regex=False)
        .str.strip()
        .replace('', None)
        .replace("", None)
        .replace("-", None)
        .astype(float)
    )
    df["score"] = df["score"] * 100

    df["state"] = "DA VALUTARE"
    df.loc[df["score"] >= 80, "state"] = "PASSATO"
    df.loc[df["score"] < 70, "state"] = "FALLITO"

    dt = pd.to_datetime(df["Total Time\nUsed"], errors="coerce")

    minutes = (dt.dt.hour * 60 + dt.dt.minute).fillna(0).astype(int)

    df["time_used"] = minutes.map(
        lambda m: f"{m // 60}h{m % 60:02d}m"
    )

    df['last_activity_date'] = pd.to_datetime(df['Last Activity Date'], errors='coerce')

    df = df.rename(columns={
        'Test': 'name',
        'Email': 'email'
    })

    df = df[[
        "name",
        "email",
        "score",
        "state",
        "time_used",
        "last_activity_date"
    ]]

    return df


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


def is_before_one_month_ago(test_last_activity):
    """
    Checks if the given datetime string (format: '2025-11-05 13:27:37.703000')
    represents a date before 1 month ago from today.

    Returns True if the activity was more than 30 days ago.
    """
    # Get current date (replace with your current date logic if needed)
    current_date = datetime.now()  # Or use: datetime(2025, 12, 16, 18, 33, 0)

    # Calculate days passed
    delta = current_date - test_last_activity
    days_passed = delta.days

    # Check if more than 30 days ago (1 month threshold)
    return days_passed > 20


def get_manatal_credentials(job_id_arg: Optional[str]) -> tuple[str, str]:
    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")

    job_id = job_id_arg or os.getenv("MANATAL_JOB_DEV_ID")
    if not job_id:
        raise SystemExit("MANATAL_JOB_DEV_ID mancante.")

    return api_key, job_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline di test Manatal -> test preliminare add notes.")
    parser.add_argument("--job-id", help="ID del job Manatal (fallback: MANATAL_JOB_DEV_ID).")

    parser.add_argument(
        "--from-stage",
        default=os.getenv("MANATAL_STAGE_FROM", "Test preliminare"),
        help='Nome dello stage di origine (default: "Test preliminare").',
    )
    parser.add_argument(
        "--to-stage",
        default=os.getenv("MANATAL_STAGE_TO", "Chiacchierata conoscitiva"),
        help='Nome dello stage di destinazione (default: "Chiacchierata conoscitiva").',
    )
    parser.add_argument(
        "--email-subject",
        default=os.getenv("PIPELINE_EMAIL_SUBJECT", "Candidatura Zupit"),
        help="Oggetto dell'email da inviare.",
    )
    parser.add_argument(
        "--email-drop-body-file",
        default=os.getenv("DROP_EMAIL_BODY_FILE"),
        help="Percorso del file di testo per il corpo email (UTF-8). Se non impostato, usa env DROP_EMAIL_BODY_FILE.",
    )
    parser.add_argument(
        "--email-chiacchierata-body-file",
        default=os.getenv("SEND_CHIACCHIERATA_EMAIL_BODY_FILE"),
        help="Percorso del file di testo per il corpo email (UTF-8). Se non impostato, usa env SEND_CHIACCHIERATA_EMAIL_BODY_FILE.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Non spostare né inviare email; stampa solo cosa farebbe.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=2.0,
        help="Secondi di pausa tra un candidato e il successivo (default: 0).",
    )
    args = parser.parse_args()

    api_key, job_id = get_manatal_credentials(args.job_id)
    headers = build_headers(api_key)

    print(f"Getting map stages...")
    stage_map = fetch_stage_ids(headers, [args.from_stage, args.to_stage])
    from_stage_id = stage_map.get(args.from_stage)
    to_stage_id = stage_map.get(args.to_stage)
    if from_stage_id is None:
        raise SystemExit(f"Stage non trovato: {stage_map}")
    if to_stage_id is None:
        raise SystemExit(f"Stage non trovato: {stage_map}")

    print(f"Cerco match in '{args.from_stage}' per job {job_id}...")
    matches = fetch_job_matches(headers, job_id, from_stage_id, stage_name=args.from_stage, page_size=200)
    print(f"Trovati {len(matches)} match nello stage di origine.")

    print(f"Getting candidates...")
    selected: List[Tuple[Dict[str, object], Dict[str, object]]] = []
    for match in matches:
        cand_id = int(match["candidate"])
        candidate = fetch_candidate(headers, cand_id)
        selected.append((match, candidate))
        time.sleep(1)

    print(f"Da processare: {len(selected)} test.")
    gmail_user = os.getenv("GMAIL_USER")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
    subject = args.email_subject

    body_drop_template_path = args.email_drop_body_file
    body_drop_template: Optional[str] = None
    if body_drop_template_path:
        try:
            body_drop_template = Path(body_drop_template_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SystemExit("Corpo email mancante: passa --email-body-file o imposta PIPELINE_EMAIL_BODY_FILE.")

    body_chiacchierata_template_path = args.email_chiacchierata_body_file
    body_chiacchierata_template: Optional[str] = None
    if body_chiacchierata_template_path:
        try:
            body_chiacchierata_template = Path(body_chiacchierata_template_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SystemExit("Corpo email mancante: passa --email-body-file o imposta PIPELINE_EMAIL_BODY_FILE.")

    df = format_excel("testDome.xlsx")

    for idx, (match, candidate) in enumerate(selected, start=1):

        print("")

        cand_fullname = str(candidate.get("full_name") or "").strip().title()
        cand_first_name = cand_fullname.split()[0] if cand_fullname else ""
        match_id = int(match["id"])
        cand_email = str(candidate.get("email") or "").strip()
        test_df = df[df["email"] == cand_email]

        test_count = len(test_df)

        if test_count == 0: # vuol dire che non ha ancora cliccato il link,
            print(f"Candidato con email: {cand_email} non ha aperto il test --> non faccio nulla")
            # TO DO controllare data spostamento colonna e droppare se > di 1 mese con nota "Non ha cliccato il link del test"
            continue
        elif test_count > 2:
            print(f"{test_count} test con email: {cand_email} --> non faccio nulla")
            continue

        test = test_df.iloc[0]

        test_name = test["name"]
        test_score = test["score"]
        test_time_used = test["time_used"]
        test_state = test["state"]
        test_last_activity = test["last_activity_date"]
        test_sent_more_than_20_days_ago = is_before_one_month_ago(test_last_activity)

        print(f"{cand_fullname} - {cand_email}")
        print(f"{test_name}")
        print(f"{test_score}/100 | ({test_time_used}) - {test_last_activity}")

        send_email = True
        if pd.isna(test_score) or test_score == 0:
            test_score = 0
            if test_sent_more_than_20_days_ago:
                send_email = False

        if has_testdome_note(match_id, headers=headers):
            print(f"Nota 'TestDome' già presente --> non faccio nulla.")
            continue

        note_text = (
            f"Testdome: {test_score}% {test_name} {test_time_used}\n"
            f"{test_state}"
        )

        url: Optional[str] = f"{API_BASE}/matches/{match_id}/notes/"
        response = requests.post(url, json={"info": note_text}, headers=headers)
        response.raise_for_status()

        if test["state"] == "PASSATO":
            print("  Test passato")
            move_match(headers, match_id, to_stage_id)
            print(f"  Spostato in '{args.to_stage}'.")

            if gmail_user and gmail_app_password and cand_email:
                body = body_chiacchierata_template.format(name=cand_first_name)
                send_gmail(gmail_user, gmail_app_password, cand_email, subject, body)
                print("  Email chiacchierata inviata.")
            else:
                print("  Email NON inviata (credenziali o email mancanti).")

        if test["state"] == "FALLITO":
            print("  Test fallito")
            drop_candidate(headers, int(match_id))
            print(f"  Candidato droppato.")

            if not send_email:
                print("  Email non inviata perché test neanche fatto")
                continue

            if gmail_user and gmail_app_password and cand_email:
                body = body_drop_template.format(name=cand_first_name)
                send_gmail(gmail_user, gmail_app_password, cand_email, subject, body)
                print("  Email drop inviata.")
            else:
                print("  Email NON inviata (credenziali o email mancanti).")

        if args.pause > 0 and idx < len(selected):
            time.sleep(args.pause)

        time.sleep(8)



if __name__ == "__main__":
    main()
