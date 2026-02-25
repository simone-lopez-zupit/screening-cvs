import time

from dotenv import load_dotenv
from requests.exceptions import HTTPError

from services.manatal_service import (
    build_headers,
    fetch_stage_ids,
    fetch_job_matches,
    create_match,
    drop_candidate,
)

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
import os
SOURCE_JOB_ID = os.getenv("SCREENING_PARAM_SOURCE_JOB_ID", "3301964")
TARGET_JOB_ID = os.getenv("SCREENING_PARAM_TARGET_JOB_ID", "303943")
STAGE_NAME = os.getenv("SCREENING_PARAM_STAGE_NAME", "Da droppare")
SLEEP_SECONDS = 2


def main() -> None:
    headers = build_headers()

    stage_map = fetch_stage_ids(headers, [STAGE_NAME])
    stage_id = stage_map.get(STAGE_NAME)
    if stage_id is None:
        raise SystemExit(f"Stage non trovato: '{STAGE_NAME}'")

    print(f"Cerco match in '{STAGE_NAME}' per job {SOURCE_JOB_ID}...")
    matches = fetch_job_matches(headers, SOURCE_JOB_ID, stage_id, stage_name=STAGE_NAME, only_active=False)
    print(f"Trovati {len(matches)} match.")

    skipped = []
    processed = 0

    for idx, match in enumerate(matches, start=1):
        candidate_id = int(match["candidate"])
        print(f"\n[{idx}/{len(matches)}] Candidato {candidate_id}")

        try:
            new_match = create_match(headers, TARGET_JOB_ID, candidate_id)
        except HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                skipped.append(candidate_id)
                print(f"  SKIPPED (gia' matchato su job {TARGET_JOB_ID})")
                continue
            raise

        new_match_id = int(new_match["id"])
        print(f"  Creato match {new_match_id} su job {TARGET_JOB_ID}")

        drop_candidate(headers, new_match_id)
        print(f"  Droppato match {new_match_id}")
        processed += 1

        time.sleep(SLEEP_SECONDS)

    print(f"\nCompletato: {processed} processati, {len(skipped)} skippati.")
    if skipped:
        print(f"Skippati (gia' matchati): {skipped}")


if __name__ == "__main__":
    main()
