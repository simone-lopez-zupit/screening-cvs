import os
from datetime import datetime
from itertools import groupby
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openpyxl import Workbook

from manatal_service import build_headers, get_all_matches

OUTPUT_FIELDS = [
    "stage_name",
    "stage_rank",
    "drop",
    "standing",
    "pass",
    "total",
    "perc_pass",
    "perc_drop",
    "perc_drop_cum",
]

def parse_updated_at(match):
    updated_at = match.get("updated_at")
    if not updated_at:
        return None
    updated_at = updated_at.replace("Z", "+00:00")
    return datetime.fromisoformat(updated_at).replace(tzinfo=None)


def get_matches_grouped_by_stage(
        matches: List[Dict[str, str]],
        since: datetime,
        to: datetime) -> List[Dict[str, str]]:

    rows: List[Dict[str, str]] = []

    matches_filtered = [match for match in matches if (dt := parse_updated_at(match)) is not None and since <= dt <= to]
    matches_filtered = [match for  match in matches_filtered if match.get("rank") not in ("1", "5", "6", "7")]

    # Sort by stage first (groupby requires sorted data) and group by stage
    matches_sorted = sorted(matches_filtered, key=lambda match: match.get("job_pipeline_stage").get("rank"))
    matches_grouped = {stage: list(group)
                       for stage, group in groupby(matches_sorted,
                                                    key=lambda match: match.get("job_pipeline_stage").get("name"))}

    matches_left = len(matches_filtered)

    for (stage, matches) in matches_grouped.items():
        matches_dropped = len([m for m in matches if m.get("is_active") == False])
        matches_standing = len([m for m in matches if m.get("is_active") == True])
        matches_total = matches_left
        matches_passed = matches_left - matches_dropped - matches_standing

        row = {
            "stage_name": stage,
            "stage_rank": matches[0].get("job_pipeline_stage").get("rank", 0) if len(matches) > 0 else -1,
            "drop": matches_dropped,
            "standing": matches_standing,
            "pass": matches_passed,
            "total": matches_total,
            "perc_pass": round(matches_passed / matches_total, 2),
            "perc_drop": round(matches_dropped / matches_total, 2),
            "perc_drop_cum": round(matches_dropped / len(matches_filtered), 2),
        }
        rows.append(row)

        matches_left = matches_passed

    return rows


def write_rows_to_excel(rows: List[Dict[str, str]], output_path: Path, headers: List[str]) -> None:
    """Salva le righe su un file Excel applicando il colore sulla decisione."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)

    print(f"Excel rows number: {len(rows)}\n")
    for row in rows:
        ws.append([row.get(field, "") for field in headers])

    wb.save(output_path)


def main() -> None:
    load_dotenv()

    api_key = os.getenv("MANATAL_API_KEY")
    if not api_key:
        raise SystemExit("MANATAL_API_KEY mancante.")

    headers = build_headers(api_key)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_matches = get_all_matches(headers=headers)

    date_ranges = [
        (datetime(2022, 1, 1), datetime.today()), # full range
        (datetime(2022, 1, 1), datetime(2022, 12, 31)),  # 2022
        (datetime(2023, 1, 1), datetime(2023, 12, 31)),  # 2023
        (datetime(2024, 1, 1), datetime(2024, 12, 31)),  # 2024
        (datetime(2025, 1, 1), datetime(2025, 12, 31)),  # 2025
        (datetime(2025, 1, 1), datetime(2025, 1, 31)),   # 2025 gen
        (datetime(2025, 2, 1), datetime(2025, 2, 28)),   # 2025 feb
        (datetime(2025, 3, 1), datetime(2025, 3, 31)),   # 2025 mar
        (datetime(2025, 4, 1), datetime(2025, 4, 30)),   # 2025 apr
        (datetime(2025, 5, 1), datetime(2025, 5, 31)),   # 2025 mag
        (datetime(2025, 6, 1), datetime(2025, 6, 30)),   # 2025 giu
        (datetime(2025, 7, 1), datetime(2025, 7, 31)),   # 2025 lug
        (datetime(2025, 8, 1), datetime(2025, 8, 31)),   # 2025 ago
        (datetime(2025, 9, 1), datetime(2025, 9, 30)),   # 2025 set
        (datetime(2025, 10, 1), datetime(2025, 10, 31)), # 2025 ott
        (datetime(2025, 11, 1), datetime(2025, 11, 30)), # 2025 nov
        (datetime(2025, 12, 1), datetime(2025, 12, 31)), # 2025 dic
        (datetime(2026, 1, 1), datetime.today()),                         # 2026 gen
        (datetime(2025, 10, 1), datetime(2025, 11, 30)), # secondo giro 2025
        (datetime(2025, 12, 1), datetime.today()), # terzo giro 2025
    ]

    rows = [{}]

    for since, to in date_ranges:
        rows.append({
            "stage_name": f"Dal {since.strftime("%-d %B %Y")} al {to.strftime("%-d %B %Y")}",
        })
        matches = get_matches_grouped_by_stage(all_matches, since=since, to=to)
        rows.extend(matches)
        rows.append({})

    excel_path = Path(f"funnel_{timestamp_str}.xlsx")
    write_rows_to_excel(rows, output_path=excel_path, headers=OUTPUT_FIELDS)
    print(f"Excel salvato in: {excel_path}")


if __name__ == "__main__":
    main()
