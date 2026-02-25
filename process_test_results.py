import os
from collections import defaultdict
from datetime import datetime, timedelta
import time
from pathlib import Path

import pandas as pd
from typing import Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from config.boards import BOARDS
from services.gmail_service import send_templated_email, EMAIL_SUBJECT
from services.testdome_service import build_testdome_headers, fetch_all_test_results, TEST_STATUS_MAP
from services.manatal_service import (
    build_headers,
    fetch_stage_ids,
    fetch_all_job_matches,
    fetch_job_matches,
    fetch_candidates,
    fetch_candidate,
    fetch_matches_with_candidates,
    get_candidate_names,
    move_match,
    drop_candidate,
    has_testdome_note,
    create_note,
)

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
EMAIL_DROP_BODY_FILE = os.getenv("DROP_EMAIL_BODY_FILE")
EMAIL_CHIACCHIERATA_BODY_FILE = os.getenv("SEND_CHIACCHIERATA_EMAIL_BODY_FILE")
NON_FARE_COSE = os.getenv("SCREENING_PARAM_NON_FARE_COSE", "true").lower() == "true"
SLEEP_SECONDS = 85

# ── Toggle which boards to process ───────────────────────────────
import json as _json
BOARD_ORDER = _json.loads(os.getenv("SCREENING_PARAM_BOARD_ORDER", '["DEV", "TL"]'))
# ──────────────────────────────────────────────────────────────────


def format_df(df: pd.DataFrame):
    df['score'] = (
        df['Total Score']
        .astype(str)
        .str.replace('%', '', regex=False)
        .str.strip()
        .replace('', None)
        .replace("", None)
        .replace("-", None)
        .astype(float)
    )

    td = pd.to_timedelta(df["Total Time Used"], errors="coerce")

    minutes = (td.dt.total_seconds() / 60).fillna(0).astype(int)

    df["time_used"] = minutes.map(
        lambda m: f"{m // 60}h{m % 60:02d}m"
    )

    df['last_activity_date'] = pd.to_datetime(df['Last Activity Date'], errors='coerce')

    df = df.rename(columns={
        'Test': 'name',
        'Email': 'email',
        'Test Status': 'status',
        'Link': 'link',
    })

    df = df[[
        "name",
        "email",
        "score",
        "status",
        "time_used",
        "last_activity_date",
        "link",
    ]]

    return df



def classify_candidate(test_df):
    """Return a classification key and test row for a candidate based on their test results."""
    test_count = len(test_df)

    if test_count == 0:
        return "test_count_0", None
    if test_count >= 2:
        return "test_count_2", None

    test = test_df.iloc[0]
    test_status = test["status"]

    if test_status in ("didNotTake", "canceled", "started", "sendingInvitation", "paused"):
        return "stati_strani", test
    if test_status == "invited":
        return "invited", test
    if pd.isna(test["score"]) or test["score"] == 0:
        return "score_0", test
    if test["score"] >= 80:
        return "passati", test
    if test["score"] < 60:
        return "falliti", test
    return "da_valutare", test


def main() -> None:
    headers = build_headers()

    # TESTDOME
    testdome_headers = build_testdome_headers()
    test_results = fetch_all_test_results(testdome_headers)

    rows = []
    for test_result in test_results:
        name = str(test_result.get("name") or "").strip()
        email = str(test_result.get("email") or "").strip()
        test_result_id = test_result.get("id")
        test_link = ""
        if test_result_id is not None:
            test_link = f"https://app.testdome.com/my-candidates/report/{test_result_id}"

        test_name = str((test_result.get("test") or {}).get("name") or "").strip()
        status_raw = str(test_result.get("status") or "").strip()
        test_status = TEST_STATUS_MAP.get(status_raw, status_raw.title() if status_raw else "")

        score_raw = test_result.get("score")
        max_score_raw = test_result.get("maxScore")
        score = None
        if score_raw is not None:
            try:
                score = float(score_raw)
            except (TypeError, ValueError):
                score = None

        if score is not None:
            max_score = None
            if max_score_raw is not None:
                try:
                    max_score = float(max_score_raw)
                except (TypeError, ValueError):
                    max_score = None
            if max_score and max_score > 0 and score > 1 and max_score > 1:
                score = (score / max_score) * 100
            if 0 < score <= 1:
                score = score * 100

        total_score = ""
        if score is not None:
            total_score = f"{round(score)}%"
        elif status_raw in {"didNotTake", "canceled"}:
            total_score = "0%"

        time_taken = test_result.get("timeTaken")
        seconds_used = 0
        if time_taken not in (None, ""):
            try:
                seconds_used = int(float(time_taken))
            except (TypeError, ValueError):
                seconds_used = 0
        hours = seconds_used // 3600
        minutes = (seconds_used % 3600) // 60
        seconds = seconds_used % 60
        total_time_used = f"{hours}:{minutes:02d}:{seconds:02d}"

        activities = test_result.get("activities") or []
        last_activity_description = ""
        last_activity_date = ""
        if isinstance(activities, list) and activities:
            latest_dt = None
            latest_activity = None
            for activity in activities:
                date_str = activity.get("date")
                if not date_str:
                    continue
                try:
                    activity_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if latest_dt is None or activity_dt > latest_dt:
                    latest_dt = activity_dt
                    latest_activity = activity
            if latest_activity:
                last_activity_description = str(latest_activity.get("description") or "").strip()
                last_activity_date = latest_activity.get("date") or ""

        rows.append(
            {
                "Name": name,
                "Email": email,
                "Test": test_name,
                "Test Status": test_status,
                "Total Score": total_score,
                "Total Time Used": total_time_used,
                "Last Activity Description": last_activity_description,
                "Last Activity Date": last_activity_date,
                "Link": test_link,
            }
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "Name",
            "Email",
            "Test",
            "Test Status",
            "Total Score",
            "Total Time Used",
            "Last Activity Description",
            "Last Activity Date",
            "Link",
        ],
    )

    grouped = df.groupby("Test Status")

    for status, group in grouped:
        print(f"\n=== {status} ({len(group)}) ===")
        for _, row in group.iterrows():
            print(
                f"{row['Name']:<25} | "
                f"{row['Email']:<30} | "
                f"{row['Test']}"
            )

    print("")
    print("----")
    print("")

    df = format_df(df)

    for board in BOARD_ORDER:
        cfg = BOARDS[board]
        job_id = cfg["job_id"]
        from_stage = cfg["stages"]["test_preliminare"]
        to_stage = cfg["stages"]["chiacchierata"]

        print(f"\n══ {board} / {from_stage} ══")

        stage_map = fetch_stage_ids(headers, [from_stage, to_stage])
        from_stage_id = stage_map.get(from_stage)
        to_stage_id = stage_map.get(to_stage)

        print(f"Cerco match in '{from_stage}' per job {job_id}...")
        selected = fetch_matches_with_candidates(headers, job_id, from_stage_id, stage_name=from_stage)
        print(f"Trovati {len(selected)} match nello stage di origine.")

        counts = {
            "passati": 0,
            "falliti": 0,
            "da_valutare": 0,
            "test_count_0": 0,
            "test_count_2": 0,
            "stati_strani": 0,
            "invited": 0,
            "score_0": 0,
        }
        summary_rows: list[tuple[str, str, str, str, str]] = []

        for idx, (match, candidate) in enumerate(selected, start=1):
            cand_id = int(match.get("candidate"))
            cand_fullname, cand_first_name = get_candidate_names(candidate)
            cand_email = str(candidate.get("email") or "").strip()
            match_id = int(match.get("id"))
            test_df = df[df["email"] == cand_email]

            print(f"{cand_fullname:<25}  |  email: {cand_email:<30}  |  id: {cand_id:<10}  |  match: {match_id:<10}")

            category, test = classify_candidate(test_df)
            counts[category] += 1

            if test is not None:
                print(f"  Test: {test['name']}  |  Score: {test['score']}/100  |  ({test['time_used']}) - {test['last_activity_date']}")

            if category == "test_count_2":
                print(f"  Test count 2.")
            elif category == "score_0":
                print(f"  Score 0.")
            elif category == "da_valutare":
                print(f"  Da valutare.")

            manatal_link = f"https://app.manatal.com/candidates/{cand_id}"
            test_name = test["name"] if test is not None else ""
            test_score = f"{test['score']}/100" if test is not None and pd.notna(test["score"]) else ""
            test_time = test["time_used"] if test is not None else ""
            summary_rows.append((manatal_link, cand_email, test_name, test_score, test_time))

            # Write testdome note
            if category in ("passati", "falliti", "da_valutare"):
                if not has_testdome_note(cand_id, headers=headers):
                    create_note(headers, cand_id,
                                f"Testdome: {test['score']}%  |  {test['name']}  |  ({test['time_used']})\nLink: {test['link']}")

            if NON_FARE_COSE or test is None:
                continue

            # Act on classification
            if category == "score_0":
                drop_candidate(headers, int(match_id))
            elif category == "passati":
                move_match(headers, match_id, to_stage_id)
                print(f"  Test passato -> spostato in '{to_stage}'.")
                if EMAIL_CHIACCHIERATA_BODY_FILE:
                    send_templated_email(cand_email, EMAIL_SUBJECT, EMAIL_CHIACCHIERATA_BODY_FILE, cand_first_name)
                    time.sleep(SLEEP_SECONDS)
            elif category == "falliti":
                drop_candidate(headers, int(match_id))
                print(f"  Droppato.")
                if EMAIL_DROP_BODY_FILE:
                    send_templated_email(cand_email, EMAIL_SUBJECT, EMAIL_DROP_BODY_FILE, cand_first_name)
                    time.sleep(SLEEP_SECONDS)

        print("")
        for key, value in counts.items():
            print(f"{key}: {value}")
        print("Totale:", sum(counts.values()))

        print(f"\n── Riepilogo {board} ──")
        for link, email, t_name, t_score, t_time in summary_rows:
            print(f"{link} ({email}) | {t_name} | {t_score} | {t_time}")


if __name__ == "__main__":
    main()
