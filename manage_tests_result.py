import argparse
import os
from collections import defaultdict
from datetime import datetime, timedelta
import time
from ftplib import all_errors
from pathlib import Path

import pandas as pd
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from services.gmail_service import send_gmail
from services.manatal_service import (
    build_headers,
    fetch_stage_ids,
    fetch_all_job_matches,
    fetch_job_matches,
    fetch_candidates,
    fetch_candidate,
    move_match,
    drop_candidate,
    has_testdome_note,
    create_note,
)

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
JOB_ID        = 303943  # DEV
# JOB_ID      = 3349722  # MAUI
FROM_STAGE    = "Test preliminare"
TO_STAGE      = "Chiacchierata conoscitiva"
EMAIL_SUBJECT = "Candidatura Zupit"
NON_FARE_COSE = True
SLEEP_SECONDS = 85
# ──────────────────────────────────────────────────────────────────────


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


def is_before_one_month_ago(test_last_activity):
    """
    Checks if the given datetime string (format: '2025-11-05 13:27:37.703000')
    represents a date before 1 month ago from today.

    Returns True if the activity was more than 30 days ago.
    """
    # Get current date (replace with your current date logic if needed)
    current_date = datetime.now()  # Or use: datetime(2025, 12, 16, 18, 33, 0)

    # Calculate days passed
    delta = current_date - test_last_activity
    days_passed = delta.days

    # Check if more than 30 days ago (1 month threshold)
    return days_passed > 20


def get_manatal_credentials() -> str:
    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")

    return api_key


def parse_match_datetime(date_str: str) -> datetime:
    """Parse ISO 8601 con Z → naive datetime."""
    if date_str.endswith('Z'):
        date_str = date_str[:-1] + '+00:00'
    return datetime.fromisoformat(date_str).replace(tzinfo=None)


def extract_possible_cheating(df: pd.DataFrame):
    time_parts = df["time_used"].astype(str).str.extract(r"(?P<hours>\d+)h(?P<minutes>\d{2})m")
    minutes = (
            time_parts["hours"].astype(float) * 60
            + time_parts["minutes"].astype(float)
    )
    cheating_candidates = df[
        (df["score"] >= 80)
        & minutes.notna()
        & (minutes < 40)
        ]
    cheating_candidates.to_csv("possible_cheating_candidates.csv", index=False)


def extract_to_evaluate(df: pd.DataFrame):
    to_evaluate_candidates = df["score"].between(60, 79)
    to_evaluate_candidates.to_csv("candidates_to_evaluate.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline di test Manatal -> test preliminare add notes.")
    parser.add_argument("--email-drop-body-file", default=os.getenv("DROP_EMAIL_BODY_FILE"))
    parser.add_argument("--email-chiacchierata-body-file", default=os.getenv("SEND_CHIACCHIERATA_EMAIL_BODY_FILE"))

    args = parser.parse_args()

    api_key = get_manatal_credentials()
    headers = build_headers(api_key)

    # TESTDOME
    testdome_client_id = os.getenv("TEST_DOME_CLIENT_ID")
    testdome_client_secret = os.getenv("TEST_DOME_CLIENT_SECRET")

    token_response = requests.post(
        url="https://api.testdome.com/token",
        data={
            "grant_type": "client_credentials",
            "client_id": testdome_client_id,
            "client_secret": testdome_client_secret,
        },
        timeout=30,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise SystemExit("Access token TestDome mancante.")

    testdome_headers = {"Authorization": f"Bearer {access_token}"}

    # GMAIL
    gmail_user = os.getenv("GMAIL_USER")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")

    body_chiacchierata_template_path = args.email_chiacchierata_body_file
    body_chiacchierata_template = Path(body_chiacchierata_template_path).read_text(encoding="utf-8")
    body_drop_template_path = args.email_drop_body_file
    body_drop_template = Path(body_drop_template_path).read_text(encoding="utf-8")

    print(f"Getting map stages...")
    stage_map = fetch_stage_ids(headers, [FROM_STAGE, TO_STAGE])
    from_stage_id = stage_map.get(FROM_STAGE)
    to_stage_id = stage_map.get(TO_STAGE)

    print(f"Cerco match in '{FROM_STAGE}' per job {JOB_ID}...")
    matches = fetch_job_matches(headers, JOB_ID, from_stage_id, stage_name=FROM_STAGE, page_size=200)
    print(f"Trovati {len(matches)} match nello stage di origine.")

    print(f"Getting candidates...")
    selected: List[Tuple[Dict[str, object], Dict[str, object]]] = []
    for match in matches:
        cand_id = int(match["candidate"])
        candidate = fetch_candidate(headers, cand_id)
        selected.append((match, candidate))
        time.sleep(.5)

    # GET TEST RESULTS from TESTDOME
    test_results: List[Dict[str, object]] = []
    skip = 0
    top = 100
    while True:
        params = {"$top": top, "$skip": skip, "$expand": ["test", "activities"]}
        response = requests.get(
            "https://api.testdome.com/v3/candidates",
            headers=testdome_headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        test_results.extend(payload.get("value", []))
        if not payload.get("hasMoreItems"):
            break
        skip += top
        time.sleep(0.5)

    test_status_map = {
        "invited": "Invited",
        "started": "Started",
        "completed": "Completed",
        "didNotTake": "Didn't take",
        "canceled": "Canceled",
        "sendingInvitation": "Sending invitation",
        "paused": "Paused",
    }

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
        test_status = test_status_map.get(status_raw, status_raw.title() if status_raw else "")

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

    # df.to_csv("testdome_results.csv", index=False)
    df = format_df(df)
    # df.to_csv("testdome_results_formatted.csv", index=False)
    # extract_possible_cheating(df)
    # extract_to_evaluate(df)

    non_fare_cose = NON_FARE_COSE

    passati_80 = 0
    falliti_60 = 0
    da_valutare = 0
    test_count_0 = 0
    test_count_2 = 0
    stati_strani = 0
    invited = 0
    score_0 = 0

    # Passato, fallito
    for idx, (match, candidate) in enumerate(selected, start=1):
        cand_id = int(match.get("candidate"))
        cand_fullname = str(candidate.get("full_name") or "").strip().title()
        cand_first_name = cand_fullname.split()[0] if cand_fullname else ""
        cand_email = str(candidate.get("email") or "").strip()
        match_id = int(match.get("id"))
        test_df = df[df["email"] == cand_email]

        print(f"{cand_fullname:<25}  |  email: {cand_email:<30}  |  id: {cand_id:<10}  |  match: {match_id:<10}")

        test_count = len(test_df)

        if test_count == 0:
            # print(f"  Test non fatto -> continue.")
            test_count_0 += 1
            continue

        if test_count >= 2:
            # print(f"  {test_count} test con email: {cand_email} --> non faccio nulla")
            test_count_2 += 1
            print(f"  Test count 2.")

            continue

        test = test_df.iloc[0]

        test_name = test["name"]
        test_status = test["status"]
        test_score = test["score"]
        test_time_used = test["time_used"]
        test_last_activity = test["last_activity_date"]
        test_link = test["link"]

        print(f"  Test: {test_name}  |  Score: {test_score}/100  |  ({test_time_used}) - {test_last_activity}")

        if test_status in ("didNotTake", "canceled", "started", "sendingInvitation", "paused"):
            # print(f"  Status: {test_status} --> continue")
            stati_strani += 1
            continue

        if test_status == "invited":
            # print(f"  Status: {test_status} | Google Form compilato, Test non ancora fatto")
            invited += 1
            #   PASSATE <= 2 settimane --> reminder
            #   PASSATE > 2 settimane --> drop
            continue

        if pd.isna(test_score) or test_score == 0:
            score_0 += 1
            print(f"  Score 0.")

            if non_fare_cose:
                continue

            drop_candidate(headers, int(match_id))
            print(f"  Score: 0 --> continue")
            continue

        if not has_testdome_note(cand_id, headers=headers):
            note_text = (
                f"Testdome: {test_score}%  |  {test_name}  |  ({test_time_used})\n"
                f"Link: {test_link}"
            )
            create_note(headers, cand_id, note_text)

        if test_score >= 80:
            print(f"{cand_email}|{test_name}|{test_score}|{test_time_used}|{test_last_activity}")
            passati_80 += 1

            if non_fare_cose:
                continue

            move_match(headers, match_id, to_stage_id)
            print(f"  Test passato -> spostato in '{TO_STAGE}'.")

            if gmail_user and gmail_app_password and cand_email:
                body = body_chiacchierata_template.format(name=cand_first_name)
                send_gmail(gmail_user, gmail_app_password, cand_email, EMAIL_SUBJECT, body)
                time.sleep(SLEEP_SECONDS)
                print("  Email chiacchierata inviata.")
            else:
                print("  Email NON inviata (credenziali o email mancanti).")

        elif test_score < 60:
            falliti_60 += 1

            print(f"  Test fallito.")
            if non_fare_cose:
                continue

            drop_candidate(headers, int(match_id))
            print(f"  Droppato.")

            if gmail_user and gmail_app_password and cand_email:
                body = body_drop_template.format(name=cand_first_name)
                send_gmail(gmail_user, gmail_app_password, cand_email, EMAIL_SUBJECT, body)
                time.sleep(SLEEP_SECONDS)
                print("  Email drop inviata.")
            else:
                print("  Email NON inviata (credenziali o email mancanti).")

        else:
            da_valutare += 1
            print(f"  Da valutare.")

            continue

    print("")
    print("passati:", passati_80)
    print("falliti:", falliti_60)
    print("da_valutare:", da_valutare)
    print("test_count_0:", test_count_0)
    print("test_count_2:", test_count_2)
    print("stati_strani:", stati_strani)
    print("invited:", invited)
    print("score_0:", score_0)

    totale = sum([passati_80, falliti_60, da_valutare, test_count_0, test_count_2, stati_strani, invited, score_0])
    print("Totale:", totale)


if __name__ == "__main__":
    main()
