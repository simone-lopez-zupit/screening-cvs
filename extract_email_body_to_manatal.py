"""
Gmail → Manatal Note Sync
=========================
Searches Gmail for emails whose subject starts with "RECRUITMENT - ",
builds a dict {sender_email: body}, then creates a note on the matching
Manatal candidate for each one.

Prerequisites
-------------
1.  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib requests
2.  Enable the Gmail API in Google Cloud Console.
3.  Download OAuth 2.0 credentials JSON → save as `credentials.json` in the same folder.
4.  Set your Manatal API token below (Enterprise Plus plan required).

First run will open a browser for Google OAuth consent; a `token.json`
file is cached so subsequent runs are non-interactive.
"""

import base64
import json
import logging
import logging.handlers
import re
import os
import time

from dotenv import load_dotenv
load_dotenv()

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from manatal_service import (
    build_headers,
    fetch_job_matches as _service_fetch_job_matches,
    fetch_stage_ids,
    fetch_candidate,
    has_gmail_sync_note,
    create_candidate_note,
    NOTE_TAG,
)

# ──────────────────────────────────────────────
# LOGGING — daily rotation, 7-day retention
# ──────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log = logging.getLogger("gmail_manatal")
log.setLevel(logging.DEBUG)

_file_handler = logging.handlers.TimedRotatingFileHandler(
    filename=os.path.join(LOG_DIR, "gmail_manatal.log"),
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
_file_handler.suffix = "%Y-%m-%d"

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("%(levelname)-8s  %(message)s"))

log.addHandler(_file_handler)
log.addHandler(_console_handler)

# ──────────────────────────────────────────────
# CONFIGURATION — edit these values
# ──────────────────────────────────────────────
GMAIL_CREDENTIALS_FILE = "google-oauth-credentials.json"   # OAuth client-secret file (Desktop app)
GMAIL_TOKEN_FILE       = "token.json"         # cached refresh token
GMAIL_SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_MAX_RESULTS      = 50                   # max emails to fetch per run

stage_names_dev   = [
    "Nuova candidatura",
    "Interessante - per futuro",
    "Test preliminare",
    "Chiacchierata conoscitiva",
    "Feedback chiacchierata conoscitiva",
    "Colloquio tecnico",
    "Live coding",
]
stage_names_tl   = [
    "Nuova candidatura (TL)",
    "Interessante - per futuro (TL)",
    "Test preliminare (TL)",
    "Chiacchierata conoscitiva (TL)",
    "Feedback chiacchierata conoscitiva (TL)",
    "Colloquio tecnico (TL)",
    "Test pratico chiacchierata con FD (TL)",
    "Approfondimenti (TL)",
    "Proposta (TL)",
]

BOARDS = {
    "TL": {
        "job_id": os.getenv("MANATAL_JOB_TL_ID", "2381880"),
        "stage_names": stage_names_tl,
        "subject_prefix": "RECRUITMENT Candidatura Spontanea [Technical Lead]",
    },
    "DEV": {
        "job_id": os.getenv("MANATAL_JOB_DEV_ID", "303943"),
        "stage_names": stage_names_dev,
        "subject_prefix": "RECRUITMENT Candidatura Spontanea [Mid/Senior Dev]",
    },
}

# ── Change this to switch board ───────────────────────────────────
BOARD = "TL"
# ──────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────
# 1. GMAIL — authenticate & fetch emails
# ──────────────────────────────────────────────
def get_gmail_service():
    """Authenticate with Gmail API and return a service object."""
    creds = None
    log.debug("Looking for token file: %s (exists: %s)", GMAIL_TOKEN_FILE, os.path.exists(GMAIL_TOKEN_FILE))
    log.debug("Credentials file: %s (exists: %s)", GMAIL_CREDENTIALS_FILE, os.path.exists(GMAIL_CREDENTIALS_FILE))

    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)
        log.debug("Loaded cached credentials — valid: %s, expired: %s", creds.valid, creds.expired)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.debug("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            log.debug("No valid credentials — starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    # Log authenticated user
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    log.info("Authenticated as: %s", profile.get("emailAddress"))
    return service


def _decode_body(payload: dict) -> str:
    """Recursively extract the plain-text body from a Gmail message payload."""
    # Single-part message
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multi-part: look for text/plain first, then text/html as fallback
    parts = payload.get("parts", [])
    plain, html = "", ""
    for part in parts:
        mime = part.get("mimeType", "")
        if mime == "text/plain" and part.get("body", {}).get("data"):
            plain = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        elif mime == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        elif mime.startswith("multipart/"):
            nested = _decode_body(part)
            if nested:
                return nested

    return plain or html


def _extract_email(from_header: str) -> str:
    """Pull the bare email address from a 'From' header like 'Name <addr>'."""
    match = re.search(r"<([^>]+)>", from_header)
    return match.group(1).lower() if match else from_header.strip().lower()


def fetch_recruitment_email_for(service, email: str, subject_prefix: str) -> dict | None:
    """
    Search Gmail for a recruitment email from a specific sender.
    Returns {"subject": ..., "body": ...} or None.
    """
    query = f'from:{email} subject:"RECRUITMENT Candidatura Spontanea" after:2025/10/16'
    log.debug("Gmail query for %s: %s", email, query)

    results = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
    messages = results.get("messages", [])

    if not messages:
        log.debug("  No Gmail messages found for %s", email)
        return None

    for msg_meta in messages:
        msg = service.users().messages().get(userId="me", id=msg_meta["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("Subject", "")

        if not subject.startswith(subject_prefix):
            log.debug("  SKIPPED — %r", subject)
            continue

        raw_body = _decode_body(msg["payload"])

        # Extract only "Informazioni aggiuntive" section
        marker = "Informazioni aggiuntive:"
        idx = raw_body.find(marker)
        if idx == -1:
            log.debug("  No 'Informazioni aggiuntive' for %s", email)
            return None

        body = raw_body[idx + len(marker):].strip()
        log.info("  Found email body for %s (%d chars)", email, len(body))
        return {"subject": subject, "body": body}

    return None


# ──────────────────────────────────────────────
# 2. MANATAL — look up candidate & create note
# ──────────────────────────────────────────────

def _fetch_job_matches_for_stage(headers: dict, job_id: str, stage_name: str) -> list[dict]:
    """Fetch all active matches for a job in a given stage."""
    stage_map = fetch_stage_ids(headers, [stage_name])
    stage_id = stage_map.get(stage_name)

    if not stage_id:
        log.error("Stage '%s' not found in Manatal.", stage_name)
        return []

    log.info("Stage '%s' → id %d", stage_name, stage_id)

    matches = _service_fetch_job_matches(
        headers, job_id, stage_id, stage_name=stage_name, page_size=200, only_active=True,
    )
    log.info("Found %d matches in '%s' for job %s", len(matches), stage_name, job_id)
    return matches


# ──────────────────────────────────────────────
# 3. MAIN — glue it all together
# ──────────────────────────────────────────────
def main():
    manatal_api_key = os.getenv("MANATAL_API_KEY", "")
    if not manatal_api_key:
        log.error("MANATAL_API_KEY env var not set.")
        return

    headers = build_headers(manatal_api_key)

    dry_run       = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
    limit         = int(os.getenv("LIMIT", "0"))
    save_file     = os.getenv("SAVE_FILE", "")

    cfg = BOARDS[BOARD]
    job_id = cfg["job_id"]
    stage_names = cfg["stage_names"]
    subject_prefix = cfg["subject_prefix"]

    # Step 1 — Get matches from all stages
    matches = []
    seen_candidates = set()
    for stage_name in stage_names:
        log.info("Fetching matches for job %s, stage '%s'...", job_id, stage_name)
        stage_matches = _fetch_job_matches_for_stage(headers, job_id, stage_name)
        for m in stage_matches:
            cid = int(m["candidate"])
            if cid not in seen_candidates:
                seen_candidates.add(cid)
                matches.append(m)
    log.info("Total unique candidates across all stages: %d", len(matches))
    if not matches:
        log.warning("No matches found.")
        return

    if limit:
        log.info("Will stop after %d note(s) created.", limit)

    # Step 2 — For each match, get candidate email, then search Gmail
    gmail_service = get_gmail_service()

    matched = []
    no_email_body = []

    for match in matches:
        if limit and len(matched) >= limit:
            log.info("Reached note limit (%d), stopping.", limit)
            break

        cand_id = int(match["candidate"])
        time.sleep(0.5)
        candidate = fetch_candidate(headers, cand_id)
        cand_email = (candidate.get("email") or "").lower().strip()
        cand_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()

        if not cand_email:
            log.warning("  %s (id %s) — no email on Manatal, skipping.", cand_name, cand_id)
            no_email_body.append(cand_name)
            continue

        log.info("Processing %s (%s)...", cand_name, cand_email)

        # Check if note already exists
        if has_gmail_sync_note(headers, cand_id):
            log.info("  SKIP — already has a %s note", NOTE_TAG)
            continue

        # Search Gmail for this candidate's recruitment email
        email_data = fetch_recruitment_email_for(gmail_service, cand_email, subject_prefix)
        if not email_data:
            log.debug("  No recruitment email with 'Informazioni aggiuntive' for %s", cand_email)
            no_email_body.append(cand_name)
            continue

        preview = email_data["body"][:200].replace("\n", " ")
        log.info("  %s → %s…", cand_email, preview)
        matched.append((cand_email, cand_id, cand_name, email_data))

    log.info("── Summary: %d with email body, %d without ──", len(matched), len(no_email_body))

    if not matched:
        log.warning("Nothing to do.")
        return

    # Save to file if requested
    if save_file:
        output = []
        for cand_email, cand_id, cand_name, data in matched:
            output.append({
                "name": cand_name,
                "email": cand_email,
                "candidate_id": cand_id,
                "subject": data["subject"],
                "body": data["body"],
                "note": f"{NOTE_TAG} **{data['subject']}**\n\n{data['body']}",
            })
        with open(save_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        log.info("Saved %d matched note(s) to %s", len(output), save_file)
        return

    # Step 3 — Create notes on Manatal
    if dry_run:
        log.info("── DRY RUN — skipping note creation ──")
        return

    created = 0
    for cand_email, cand_id, cand_name, data in matched:
        time.sleep(0.5)
        try:
            result = create_candidate_note(
                headers=headers,
                candidate_pk=cand_id,
                note_content=data["body"],
                subject=data["subject"],
            )
            log.info("Note created for %s (%s), note id: %s", cand_name, cand_email, result.get("id"))
            created += 1
        except requests.HTTPError as exc:
            log.error("Failed to create note for %s: %s", cand_name, exc)

    log.info("Done — created: %d notes", created)


if __name__ == "__main__":
    main()
