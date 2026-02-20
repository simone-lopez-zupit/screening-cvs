"""
Gmail service — shared helpers for sending emails and reading via Gmail API.
"""

import base64
import logging
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

log = logging.getLogger("gmail_service")

# ── Configuration ─────────────────────────────────────────────────────
GMAIL_CREDENTIALS_FILE = "config/google-oauth-credentials.json"
GMAIL_TOKEN_FILE       = "config/token.json"
GMAIL_SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_MAX_RESULTS      = 50
EMAIL_SUBJECT          = "Candidatura Zupit"


# ── Send (SMTP) ──────────────────────────────────────────────────────

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


def send_templated_email(
    to_email: str,
    subject: str,
    template_path: str,
    name: str,
) -> None:
    """Load template from file, format with {name}, and send via SMTP."""
    user = os.getenv("GMAIL_USER", "")
    app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    if not user or not app_password or not to_email:
        return
    body = Path(template_path).read_text(encoding="utf-8").format(name=name)
    send_gmail(user, app_password, to_email, subject, body)


# ── Read (Gmail API) ─────────────────────────────────────────────────

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


def decode_body(payload: dict) -> str:
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
            nested = decode_body(part)
            if nested:
                return nested

    return plain or html


def extract_email(from_header: str) -> str:
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

        raw_body = decode_body(msg["payload"])

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
