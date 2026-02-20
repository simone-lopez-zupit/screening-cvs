import os
import time

from dotenv import load_dotenv
import requests

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
    STAGE_NAMES_DEV,
    STAGE_NAMES_TL,
)

load_dotenv()

# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────
BOARDS = {
    "TL": {
        "job_id": os.getenv("MANATAL_JOB_TL_ID", "2381880"),
        "stage_names": STAGE_NAMES_TL,
        "subject_prefix": "RECRUITMENT Candidatura Spontanea [Technical Lead]",
    },
    "DEV": {
        "job_id": os.getenv("MANATAL_JOB_DEV_ID", "303943"),
        "stage_names": STAGE_NAMES_DEV,
        "subject_prefix": "RECRUITMENT Candidatura Spontanea [Mid/Senior Dev]",
    },
}

# ── Order in which boards are processed ───────────────────────────
BOARD_ORDER = ["TL", "DEV"]
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
        log.warning("No matches found for %s.", board_name)
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

        # Search Gmail for this candidate's recruitment email
        email_data = fetch_recruitment_email_for(gmail_service, cand_email, subject_prefix)
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
