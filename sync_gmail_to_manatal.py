import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import requests

from config.boards import BOARDS
from services.gmail_service import get_gmail_service, fetch_recruitment_email_for
from services.logging_config import setup_logger
from services.manatal_service import (
    build_headers,
    fetch_job_matches as _service_fetch_job_matches,
    fetch_stage_ids,
    fetch_candidate,
    has_gmail_sync_note,
    create_candidate_note,
    NOTE_TAG,
)

load_dotenv()

# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────
SUBJECT_PREFIXES = {
    "TL": ["RECRUITMENT Candidatura Spontanea [Technical Lead]"],
    "DEV": [
        "RECRUITMENT Candidatura Spontanea [Mid/Senior Dev]",
        "RECRUITMENT Candidatura Spontanea [Jun Dev]",
        "RECRUITMENT Candidatura Spontanea [Mid Dev]",
        "RECRUITMENT Candidatura Spontanea [Sen Dev]",
    ],
}

# ── Order in which boards are processed ───────────────────────────
import json as _json
BOARD_ORDER = _json.loads(os.getenv("SCREENING_PARAM_BOARD_ORDER", '["TL", "DEV"]'))
MATCH_MAX_AGE_DAYS = 30
# ──────────────────────────────────────────────────────────────────

log = setup_logger("gmail_manatal")

# ──────────────────────────────────────────────
# MANATAL — look up candidate & create note
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
def _process_board(board_name, headers, gmail_service):
    """Run the sync pipeline for a single board."""
    log.info("══ Processing board: %s ══", board_name)

    cfg = BOARDS[board_name]
    job_id = cfg["job_id"]
    stage_names = list(cfg["stages"].values())
    subject_prefixes = SUBJECT_PREFIXES[board_name]

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
        log.warning("No matches found for %s.", board_name)
        return

    # Filter matches created within the last MATCH_MAX_AGE_DAYS days
    cutoff = datetime.now(timezone.utc) - timedelta(days=MATCH_MAX_AGE_DAYS)
    before = len(matches)
    matches = [
        m for m in matches
        if datetime.fromisoformat(m["created_at"].replace("Z", "+00:00")) >= cutoff
    ]
    log.info("Filtered to %d matches created in the last %d days (excluded %d)",
             len(matches), MATCH_MAX_AGE_DAYS, before - len(matches))
    if not matches:
        log.warning("No recent matches for %s.", board_name)
        return

    # Step 2 — For each match, get candidate email, then search Gmail
    matched = []
    no_email_body = []

    for match in matches:
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

        # Search Gmail for this candidate's recruitment email (try all subject prefixes)
        email_data = None
        for prefix in subject_prefixes:
            email_data = fetch_recruitment_email_for(gmail_service, cand_email, prefix)
            if email_data:
                break
        if not email_data:
            log.debug("  No recruitment email with 'Informazioni aggiuntive' for %s", cand_email)
            no_email_body.append(cand_name)
            continue

        preview = email_data["body"][:200].replace("\n", " ")
        log.info("  %s → %s…", cand_email, preview)
        matched.append((cand_email, cand_id, cand_name, email_data))

    log.info("── Summary [%s]: %d with email body, %d without ──", board_name, len(matched), len(no_email_body))

    if not matched:
        log.warning("Nothing to do for %s.", board_name)
        return

    # Step 3 — Create notes on Manatal
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

    log.info("Done [%s] — created: %d notes", board_name, created)


def main():
    headers = build_headers()

    gmail_service = get_gmail_service()

    for board_name in BOARD_ORDER:
        _process_board(board_name, headers, gmail_service)


if __name__ == "__main__":
    main()
