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
import re
import os
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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
    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


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

    subject_prefix = "RECRUITMENT - Candidatura Spontanea [Mid/Senior Dev]"

    # Gmail search query — subject: prefix match
    query = 'subject:"' + subject_prefix + '"'
    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=GMAIL_MAX_RESULTS)
        .execute()
    )
    messages = results.get("messages", [])
    if not messages:
        print("No emails found matching the filter.")
        return {}

    emails: dict[str, dict] = {}

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
            continue

        sender = _extract_email(headers.get("From", ""))
        body = _decode_body(msg["payload"])

        # Keep only the most recent email per sender
        emails[sender] = {
            "subject": subject,
            "body": body.strip(),
        }

    print(f"Found {len(emails)} recruitment email(s).")
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
    print("\n── Email → Body mapping ─────────────────")
    for addr, data in emails.items():
        preview = data["body"][:120].replace("\n", " ")
        print(f"  {addr}  |  {data['subject']}  |  {preview}…")
    print()

    # Step 2 — Push each email body as a note in Manatal
    for sender_email, data in emails.items():
        candidate_pk = find_candidate_by_email(sender_email)

        if candidate_pk is None:
            print(f"⚠  No Manatal candidate found for {sender_email} — skipping.")
            continue

        try:
            result = create_candidate_note(
                candidate_pk=candidate_pk,
                note_content=data["body"],
                subject=data["subject"],
            )
            print(f"✓  Note created for {sender_email} (candidate {candidate_pk}), note id: {result.get('id')}")
        except requests.HTTPError as exc:
            print(f"✗  Failed to create note for {sender_email}: {exc}")


if __name__ == "__main__":
    main()