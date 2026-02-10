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
import logging
import logging.handlers
import re
import os
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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

MANATAL_API_KEY        = os.getenv("MANATAL_API_KEY")
MANATAL_BASE_URL       = "https://api.manatal.com/open/v3"


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


def fetch_recruitment_emails() -> dict[str, dict]:
    """
    Return a dict keyed by sender email:
    {
        "john@example.com": {
            "subject": "RECRUITMENT - Software Engineer",
            "body": "Full email body text …"
        },
        ...
    }
    If the same sender sent multiple matching emails, only the latest is kept.
    """
    service = get_gmail_service()

    subject_prefix = "RECRUITMENT Candidatura Spontanea [Mid/Senior Dev]"

    # Gmail search query — broad match, then filter precisely with startswith
    query = 'subject:"RECRUITMENT Candidatura Spontanea"'
    log.debug("Gmail search query: %s", query)
    log.debug("subject_prefix for startswith filter: %r", subject_prefix)
    log.debug("maxResults: %s", GMAIL_MAX_RESULTS)

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=GMAIL_MAX_RESULTS)
        .execute()
    )
    messages = results.get("messages", [])
    log.debug("Gmail API returned %d message(s) for query", len(messages))

    if not messages:
        log.warning("No emails found matching the filter.")
        # Try a broader query to help diagnose
        broad_query = "subject:RECRUITMENT"
        log.debug("Trying broader query: %s", broad_query)
        broad_results = (
            service.users()
            .messages()
            .list(userId="me", q=broad_query, maxResults=10)
            .execute()
        )
        broad_messages = broad_results.get("messages", [])
        log.debug("Broader query returned %d message(s)", len(broad_messages))
        for bm in broad_messages:
            bm_full = (
                service.users()
                .messages()
                .get(userId="me", id=bm["id"], format="metadata", metadataHeaders=["Subject"])
                .execute()
            )
            bm_headers = {h["name"]: h["value"] for h in bm_full.get("payload", {}).get("headers", [])}
            log.debug("  Subject: %r", bm_headers.get("Subject", "(none)"))
        return {}

    emails: dict[str, dict] = {}
    skipped = 0

    for msg_meta in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_meta["id"], format="full")
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("Subject", "")

        # Double-check the subject truly starts with the prefix
        if not subject.startswith(subject_prefix):
            log.debug("SKIPPED — subject does not match prefix")
            log.debug("  subject:  %r", subject)
            log.debug("  expected: %r", subject_prefix)
            skipped += 1
            continue

        sender = _extract_email(headers.get("From", ""))
        body = _decode_body(msg["payload"])
        log.info("MATCHED — sender: %s, subject: %r", sender, subject)

        # Keep only the most recent email per sender
        emails[sender] = {
            "subject": subject,
            "body": body.strip(),
        }

    log.info("Total from API: %d, matched: %d, skipped: %d", len(messages), len(emails), skipped)
    log.info("Found %d recruitment email(s).", len(emails))
    return emails


# ──────────────────────────────────────────────
# 2. MANATAL — look up candidate & create note
# ──────────────────────────────────────────────
def _manatal_headers() -> dict:
    return {
        "Authorization": f"Token {MANATAL_API_KEY}",
        "Content-Type": "application/json",
    }


def find_candidate_by_email(email: str) -> int | None:
    """Search Manatal for a candidate whose email matches. Returns candidate PK or None."""
    url = f"{MANATAL_BASE_URL}/candidates/"
    resp = requests.get(url, headers=_manatal_headers(), params={"search": email})
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results", [])
    for candidate in results:
        # Check primary email or all email fields
        candidate_email = (candidate.get("email") or "").lower()
        if candidate_email == email:
            return candidate["id"]

    return None


def create_candidate_note(candidate_pk: int, note_content: str, subject: str = "") -> dict:
    """
    POST a note on a Manatal candidate.
    Endpoint: POST /open/v3/candidates/{candidate_pk}/notes/
    """
    url = f"{MANATAL_BASE_URL}/candidates/{candidate_pk}/notes/"
    payload = {
        "note": f"**{subject}**\n\n{note_content}" if subject else note_content,
    }
    resp = requests.post(url, headers=_manatal_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────
# 3. MAIN — glue it all together
# ──────────────────────────────────────────────
def main():

    # Step 1 — Fetch recruitment emails from Gmail
    emails = fetch_recruitment_emails()
    if not emails:
        return

    # Quick preview
    log.info("── Email → Body mapping ─────────────────")
    for addr, data in emails.items():
        preview = data["body"][:120].replace("\n", " ")
        log.info("  %s  |  %s  |  %s…", addr, data["subject"], preview)

    # Step 2 — Push each email body as a note in Manatal
    for sender_email, data in emails.items():
        candidate_pk = find_candidate_by_email(sender_email)

        if candidate_pk is None:
            log.warning("No Manatal candidate found for %s — skipping.", sender_email)
            continue

        try:
            result = create_candidate_note(
                candidate_pk=candidate_pk,
                note_content=data["body"],
                subject=data["subject"],
            )
            log.info("Note created for %s (candidate %s), note id: %s", sender_email, candidate_pk, result.get("id"))
        except requests.HTTPError as exc:
            log.error("Failed to create note for %s: %s", sender_email, exc)


if __name__ == "__main__":
    main()