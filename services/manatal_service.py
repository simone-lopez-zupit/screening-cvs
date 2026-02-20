"""
Manatal API service — shared helpers used by all pipeline scripts.
"""

import os
import time
from typing import Dict, Iterable, List, Optional, Tuple

import requests

API_BASE = "https://api.manatal.com/open/v3"

NOTE_TAG = "[GMAIL_SYNC]"

def _get_api_key() -> str:
    return os.getenv("MANATAL_API_KEY", "")


# ── Internal helpers ─────────────────────────────────────────────────

def build_headers() -> Dict[str, str]:
    token = _get_api_key().strip()
    if not token.lower().startswith("token "):
        token = f"Token {token}"
    return {"Authorization": token, "Content-Type": "application/json"}



def absolute_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("http"):
        return url
    return f"{API_BASE.rstrip('/')}/{url.lstrip('/')}"


def _manatal_request(method: str, headers: Dict[str, str], url: str, **kwargs) -> requests.Response:
    """HTTP request with retry on 429 rate limit."""
    for attempt in range(5):
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        if resp.status_code == 429:
            wait = 2 ** attempt
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def _manatal_get(headers: Dict[str, str], url: str, **kwargs) -> requests.Response:
    return _manatal_request("GET", headers, url, **kwargs)


def _manatal_post(headers: Dict[str, str], url: str, **kwargs) -> requests.Response:
    return _manatal_request("POST", headers, url, **kwargs)


def _manatal_patch(headers: Dict[str, str], url: str, **kwargs) -> requests.Response:
    return _manatal_request("PATCH", headers, url, **kwargs)


# ── Stages ───────────────────────────────────────────────────────────

def fetch_stage_ids(headers: Dict[str, str], stage_names: Iterable[str]) -> Dict[str, int]:
    wanted = {name.lower(): name for name in stage_names}
    found: Dict[str, int] = {}

    url: Optional[str] = f"{API_BASE}/match-stages/?page_size=200"
    while url:
        resp = _manatal_get(headers, url)
        data = resp.json()
        for stage in data.get("results", []):
            name = str(stage.get("name") or "")
            key = name.lower()
            if key in wanted and wanted[key] not in found:
                found[wanted[key]] = int(stage["id"])
        url = absolute_url(data.get("next"))

    return found


# ── Matches ──────────────────────────────────────────────────────────

def fetch_job_matches(
    headers: Dict[str, str],
    job_id: str,
    stage_id: int,
    stage_name: Optional[str] = None,
    page_size: int = 100,
    only_active: bool = True,
) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    url: Optional[str] = f"{API_BASE}/jobs/{job_id}/matches/?page_size={page_size}"
    while url:
        data = _manatal_get(headers, url).json()
        for match in data.get("results", []):
            stage = match.get("stage") or {}
            if int(stage.get("id", -1)) != stage_id:
                continue
            if stage_name and str(stage.get("name") or "").strip().lower() != stage_name.strip().lower():
                continue
            if only_active and not match.get("is_active", False):
                continue
            matches.append(match)
        url = absolute_url(data.get("next"))
    return matches


def fetch_all_job_matches(headers: Dict[str, str]) -> List[Dict[str, object]]:
    """Fetch first page of all matches (no job filter)."""
    all_matches = []
    url = f"{API_BASE}/matches/?page_size=200"

    index = 0
    while index == 0 and url:
        index += 1
        data = _manatal_get(headers, url).json()
        all_matches.extend(data["results"])
        url = data.get("next")
    return all_matches


def get_all_matches(
    headers: Dict[str, str],
    job_id: str = "",
    page_size: int = 200,
) -> List[Dict[str, str]]:
    matches_raw: List[Dict[str, str]] = []
    url_job_matches: Optional[str] = f"{API_BASE}/jobs/{job_id}/matches/?page_size={page_size}"
    while url_job_matches:
        data = _manatal_get(headers, url_job_matches).json()
        matches_raw.extend(data.get("results", []))
        url_job_matches = absolute_url(data.get("next"))

    return matches_raw


# ── Candidate helpers ────────────────────────────────────────────────

def get_candidate_names(candidate: Dict[str, object]) -> Tuple[str, str]:
    """Return (full_name, first_name) from a candidate dict."""
    fullname = str(candidate.get("full_name") or "").strip().title()
    first_name = fullname.split()[0] if fullname else ""
    return fullname, first_name


def fetch_matches_with_candidates(
    headers: Dict[str, str],
    job_id: str,
    stage_id: int,
    stage_name: Optional[str] = None,
) -> List[Tuple[Dict[str, object], Dict[str, object]]]:
    """Fetch matches in a stage and resolve each to its candidate."""
    matches = fetch_job_matches(headers, job_id, stage_id, stage_name=stage_name, page_size=200)
    selected: List[Tuple[Dict[str, object], Dict[str, object]]] = []
    for match in matches:
        candidate = fetch_candidate(headers, int(match["candidate"]))
        selected.append((match, candidate))
    return selected


# ── Candidates ───────────────────────────────────────────────────────

def fetch_candidates(headers: Dict[str, str]) -> List[Dict[str, object]]:
    all_candidates = []
    url = f"{API_BASE}/candidates/?page_size=200"

    while url:
        data = _manatal_get(headers, url).json()
        all_candidates.extend(data["results"])
        url = data.get("next")
    return all_candidates


def fetch_candidate(headers: Dict[str, str], candidate_id: int) -> Dict[str, object]:
    return _manatal_get(headers, f"{API_BASE}/candidates/{candidate_id}/").json()


def get_candidate_info(headers: Dict[str, str], email: str):
    url_candidates: Optional[str] = f"{API_BASE}/candidates/?email={email}"
    data = _manatal_get(headers, url_candidates).json()

    candidates = data.get("results", [])

    base_link = "app.manatal.com/candidates/"

    if len(candidates) == 0:
        return "", ""
    if len(candidates) > 1:
        return "SISTEMARE", "DUPLICATI"

    cand_id = candidates[0].get("id")
    url_matches: Optional[str] = f"{API_BASE}/candidates/{cand_id}/matches/"
    data = _manatal_get(headers, url_matches).json()
    matches = data.get("results", [])

    matches = (f"{match.get('stage').get('name')}" for match in matches)

    return f"=HYPERLINK(\"{base_link}{cand_id}\")", "&CHAR(10)&".join(matches)


# ── Match mutations ──────────────────────────────────────────────────

def move_match(headers: Dict[str, str], match_id: int, stage_id: int) -> None:
    _manatal_patch(headers, f"{API_BASE}/matches/{match_id}/", json={"stage": {"id": stage_id}})


def drop_candidate(headers: Dict[str, str], match_id: int) -> None:
    _manatal_patch(headers, f"{API_BASE}/matches/{match_id}/", json={"is_active": "false"})


# ── Notes ────────────────────────────────────────────────────────────

def has_testdome_note(cand_id: int, headers: Dict[str, str]) -> bool:
    url = f"{API_BASE}/candidates/{cand_id}/notes/"
    notes = _manatal_get(headers, url).json()

    return any(
        isinstance(note.get("info"), str) and "testdome" in note["info"].lower()
        for note in notes
    )


def create_note(headers: Dict[str, str], candidate_id: int, info: str) -> dict:
    """POST a plain note on a Manatal candidate."""
    url = f"{API_BASE}/candidates/{candidate_id}/notes/"
    return _manatal_post(headers, url, json={"info": info}).json()


def has_gmail_sync_note(headers: Dict[str, str], candidate_pk: int) -> bool:
    """Check if a candidate already has a note tagged with NOTE_TAG."""
    url = f"{API_BASE}/candidates/{candidate_pk}/notes/"
    data = _manatal_get(headers, url).json()

    notes = data if isinstance(data, list) else data.get("results", [])
    for note in notes:
        note_text = note.get("note") or note.get("text") or note.get("info") or ""
        if NOTE_TAG in note_text:
            return True
    return False


def create_candidate_note(
    headers: Dict[str, str],
    candidate_pk: int,
    note_content: str,
    subject: str = "",
) -> dict:
    """POST a note on a Manatal candidate."""
    url = f"{API_BASE}/candidates/{candidate_pk}/notes/"
    payload = {
        "info": f"{NOTE_TAG} **{subject}**\n\n{note_content}" if subject else f"{NOTE_TAG}\n\n{note_content}",
    }
    return _manatal_post(headers, url, json=payload).json()
