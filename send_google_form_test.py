import os
import time

from dotenv import load_dotenv

from services.gmail_service import send_templated_email
from services.manatal_service import (
    build_headers,
    fetch_stage_ids,
    fetch_matches_with_candidates,
    get_candidate_names,
    move_match,
)


load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
BOARDS = {
    "TL": {
        "from_stage": "Test preliminare (TL)",
        "to_stage": "Colloquio tecnico (TL)",
        "job_id": os.getenv("MANATAL_JOB_TL_ID"),
        "email_subject": "Candidatura Zupit",
        "email_body_file": os.getenv("SEND_TEST_EMAIL_BODY_FILE"),
        "sleep_seconds": 33,
    },
    "DEV": {
        "from_stage": "Test preliminare",
        "to_stage": "Colloquio tecnico",
        "job_id": os.getenv("MANATAL_JOB_DEV_ID"),
        "email_subject": "Candidatura Zupit",
        "email_body_file": os.getenv("SEND_TEST_EMAIL_BODY_FILE"),
        "sleep_seconds": 33,
    },
}

# ── Change this to switch board ───────────────────────────────────
BOARD = "TL"
# ──────────────────────────────────────────────────────────────────


def main() -> None:
    cfg = BOARDS[BOARD]
    from_stage = cfg["from_stage"]
    to_stage = cfg["to_stage"]
    job_id = cfg["job_id"]
    email_subject = cfg["email_subject"]
    email_body_file = cfg["email_body_file"]
    sleep_seconds = cfg["sleep_seconds"]

    if not job_id:
        raise SystemExit("JOB_ID mancante.")

    headers = build_headers()
    stage_map = fetch_stage_ids(headers, [from_stage, to_stage])
    from_stage_id = stage_map.get(from_stage)
    to_stage_id = stage_map.get(to_stage)
    if from_stage_id is None or to_stage_id is None:
        raise SystemExit(f"Stage non trovati: {stage_map}")

    print(f"Cerco match in '{from_stage}' per job {job_id}...")
    selected = fetch_matches_with_candidates(headers, job_id, from_stage_id, stage_name=from_stage)
    print(f"Trovati {len(selected)} match nello stage di origine.")

    if not email_body_file:
        raise SystemExit("Corpo email mancante: imposta SEND_TEST_EMAIL_BODY_FILE.")

    for idx, (match, candidate) in enumerate(selected, start=1):
        cand_fullname, cand_first_name = get_candidate_names(candidate)
        cand_email = str(candidate.get("email") or "").strip()
        print(f"- Match {match['id']} / candidato #{idx} - {cand_fullname} ({cand_email or '!!! EMAIL MANCANTE !!!'})")

        # move_match(headers, int(match["id"]), to_stage_id)
        # print(f"  Spostato in '{to_stage}'.")

        send_templated_email(cand_email, email_subject, email_body_file, cand_first_name)
        if cand_email:
            print("  Email inviata.")

        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
