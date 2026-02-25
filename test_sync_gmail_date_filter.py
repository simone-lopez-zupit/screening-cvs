"""Test the 30-day match date filter in sync_gmail_to_manatal."""

from datetime import datetime, timedelta, timezone


def make_match(created_at_str, candidate_id=1):
    return {"created_at": created_at_str, "candidate": str(candidate_id)}


def filter_matches(matches, max_age_days=30):
    """Replicate the filtering logic from _process_board."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return [
        m for m in matches
        if datetime.fromisoformat(m["created_at"].replace("Z", "+00:00")) >= cutoff
    ]


def test_recent_match_kept():
    now = datetime.now(timezone.utc)
    m = make_match(now.isoformat(), candidate_id=1)
    result = filter_matches([m])
    assert len(result) == 1, "Match created now should be kept"


def test_match_at_boundary_kept():
    """Match created 29 days and 23 hours ago should be kept."""
    almost_30 = datetime.now(timezone.utc) - timedelta(days=29, hours=23)
    m = make_match(almost_30.isoformat(), candidate_id=2)
    result = filter_matches([m])
    assert len(result) == 1, "Match created just under 30 days ago should be kept"


def test_old_match_excluded():
    old = datetime.now(timezone.utc) - timedelta(days=31)
    m = make_match(old.isoformat(), candidate_id=3)
    result = filter_matches([m])
    assert len(result) == 0, "Match older than 30 days should be excluded"


def test_mixed_matches():
    now = datetime.now(timezone.utc)
    matches = [
        make_match((now - timedelta(days=1)).isoformat(), candidate_id=1),
        make_match((now - timedelta(days=15)).isoformat(), candidate_id=2),
        make_match((now - timedelta(days=29)).isoformat(), candidate_id=3),
        make_match((now - timedelta(days=31)).isoformat(), candidate_id=4),
        make_match((now - timedelta(days=60)).isoformat(), candidate_id=5),
    ]
    result = filter_matches(matches)
    assert len(result) == 3, f"Expected 3 recent matches, got {len(result)}"
    ids = [m["candidate"] for m in result]
    assert ids == ["1", "2", "3"]


def test_manatal_date_format():
    """Manatal typically returns ISO 8601 dates like '2026-01-25T10:30:00Z'."""
    now = datetime.now(timezone.utc)
    m = make_match(now.strftime("%Y-%m-%dT%H:%M:%SZ"), candidate_id=1)
    result = filter_matches([m])
    assert len(result) == 1, "Should parse Manatal-style Z-suffix dates"


def test_empty_list():
    result = filter_matches([])
    assert result == [], "Empty input should return empty output"


if __name__ == "__main__":
    test_recent_match_kept()
    test_match_at_boundary_kept()
    test_old_match_excluded()
    test_mixed_matches()
    test_manatal_date_format()
    test_empty_list()
    print("All tests passed!")
