import os
import time

from dotenv import load_dotenv

from services.gmail_service import send_templated_email, EMAIL_SUBJECT
from services.manatal_service import (
    build_headers,
    fetch_stage_ids,
    fetch_matches_with_candidates,
    get_candidate_names,
    move_match,
)


load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
EMAIL_BODY_FILE = os.getenv("SEND_TEST_EMAIL_BODY_FILE")
SLEEP_SECONDS = 33

BOARDS = {
    "TL": {"job_id": os.getenv("MANATAL_JOB_TL_ID"), "from_stage": "Test preliminare (TL)", "to_stage": "Colloquio tecnico (TL)"},
    "DEV": {"job_id": os.getenv("MANATAL_JOB_DEV_ID"), "from_stage": "Test preliminare", "to_stage": "Colloquio tecnico"},
}

# ── Toggle which boards to process ───────────────────────────────
SEND_TL = True
SEND_DEV = False
# ──────────────────────────────────────────────────────────────────


def main() -> None:
    headers = build_headers()

    boards_to_send = []
    if SEND_TL:
        boards_to_send.append("TL")
    if SEND_DEV:
        boards_to_send.append("DEV")

    for board in boards_to_send:
        cfg = BOARDS[board]
        job_id = cfg["job_id"]
        from_stage = cfg["from_stage"]
        to_stage = cfg["to_stage"]

        if not job_id:
            raise SystemExit(f"JOB_ID mancante per {board}.")

        print(f"\n══ {board} / {from_stage} ══")

        stage_map = fetch_stage_ids(headers, [from_stage, to_stage])
        from_stage_id = stage_map.get(from_stage)
        to_stage_id = stage_map.get(to_stage)
        if from_stage_id is None or to_stage_id is None:
            raise SystemExit(f"Stage non trovati: {stage_map}")

        print(f"Cerco match in '{from_stage}' per job {job_id}...")
        selected = fetch_matches_with_candidates(headers, job_id, from_stage_id, stage_name=from_stage)
        print(f"Trovati {len(selected)} match nello stage di origine.")

        for idx, (match, candidate) in enumerate(selected, start=1):
            cand_fullname, cand_first_name = get_candidate_names(candidate)
            cand_email = str(candidate.get("email") or "").strip()
            print(f"- Match {match['id']} / candidato #{idx} - {cand_fullname} ({cand_email or '!!! EMAIL MANCANTE !!!'})")

            # move_match(headers, int(match["id"]), to_stage_id)
            # print(f"  Spostato in '{to_stage}'.")

            send_templated_email(cand_email, EMAIL_SUBJECT, EMAIL_BODY_FILE, cand_first_name)
            if cand_email:
                print("  Email inviata.")

            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
