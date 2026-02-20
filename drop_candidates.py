import os
import time

from dotenv import load_dotenv

from config.boards import BOARDS
from services.gmail_service import send_templated_email, EMAIL_SUBJECT
from services.manatal_service import (
    build_headers,
    fetch_stage_ids,
    fetch_matches_with_candidates,
    get_candidate_names,
    drop_candidate,
)

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
EMAIL_BODY_FILE = os.getenv("DROP_EMAIL_BODY_FILE")
SLEEP_SECONDS = 65

# ── Toggle which boards to drop ──────────────────────────────────
DROP_TL = False
DROP_DEV = True
# ──────────────────────────────────────────────────────────────────


def main() -> None:
    headers = build_headers()

    boards_to_drop = []
    if DROP_TL:
        boards_to_drop.append("TL")
    if DROP_DEV:
        boards_to_drop.append("DEV")

    for board in boards_to_drop:
        cfg = BOARDS[board]
        job_id = cfg["job_id"]
        stage_name = cfg["stages"]["nuova_candidatura"]
        print(f"\n══ {board} / {stage_name} ══")

        stage_map = fetch_stage_ids(headers, [stage_name])
        from_stage_id = stage_map.get(stage_name)
        if from_stage_id is None:
            raise SystemExit(f"Stage non trovato: '{stage_name}'")

        print(f"Cerco match in '{stage_name}' per job {job_id}...")
        selected = fetch_matches_with_candidates(headers, job_id, from_stage_id, stage_name=stage_name)
        print(f"Trovati {len(selected)} match nello stage '{stage_name}'.")

        for idx, (match, candidate) in enumerate(selected, start=1):
            cand_fullname, cand_first_name = get_candidate_names(candidate)
            cand_email = str(candidate.get("email") or "").strip()
            print(f"- Match {match['id']} / candidato #{idx} - {cand_fullname} ({cand_email or '!!! EMAIL MANCANTE !!!'})")

            drop_candidate(headers, int(match["id"]))
            print("  Droppato.")

            send_templated_email(cand_email, EMAIL_SUBJECT, EMAIL_BODY_FILE, cand_first_name)
            print("  Email inviata.")

            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
