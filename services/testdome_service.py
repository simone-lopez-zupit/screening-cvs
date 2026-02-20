"""
TestDome API service — authentication and candidate fetching.
"""

import os
import time
from typing import Dict, List

import requests

TESTDOME_API_BASE = "https://api.testdome.com"

TEST_STATUS_MAP = {
    "invited": "Invited",
    "started": "Started",
    "completed": "Completed",
    "didNotTake": "Didn't take",
    "canceled": "Canceled",
    "sendingInvitation": "Sending invitation",
    "paused": "Paused",
}


def build_testdome_headers() -> Dict[str, str]:
    client_id = os.getenv("TEST_DOME_CLIENT_ID")
    client_secret = os.getenv("TEST_DOME_CLIENT_SECRET")

    token_response = requests.post(
        url=f"{TESTDOME_API_BASE}/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise SystemExit("Access token TestDome mancante.")

    return {"Authorization": f"Bearer {access_token}"}


def fetch_all_test_results(headers: Dict[str, str], page_size: int = 100) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    skip = 0
    while True:
        params = {"$top": page_size, "$skip": skip, "$expand": ["test", "activities"]}
        response = requests.get(
            f"{TESTDOME_API_BASE}/v3/candidates",
            headers=headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results.extend(payload.get("value", []))
        if not payload.get("hasMoreItems"):
            break
        skip += page_size
        time.sleep(0.5)
    return results
