"""
Quick script: extract emails from non-duplicate CVs, look them up in Manatal,
and print the ones found with email, job, stage, isDropped.
"""

import base64
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from screening_cvs import hash_file, find_duplicates, SYSTEM_PROMPT, MODEL
from services.manatal_service import build_headers, _manatal_get, API_BASE

load_dotenv()

INPUT_DIR = Path("cvs")


def extract_email(client, pdf_path):
    with pdf_path.open("rb") as f:
        pdf_bytes = f.read()
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "file", "file": {"filename": pdf_path.name, "file_data": f"data:application/pdf;base64,{b64}"}},
                {"type": "text", "text": 'Estrai solo l\'email dal CV. Rispondi con: {"email": ""}'},
            ]},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    return (data.get("email") or "").strip()


def lookup_manatal(headers, email):
    data = _manatal_get(headers, f"{API_BASE}/candidates/?email={email}").json()
    candidates = data.get("results", [])
    if not candidates:
        return None

    cand = candidates[0]
    cand_id = cand["id"]

    matches_data = _manatal_get(headers, f"{API_BASE}/candidates/{cand_id}/matches/").json()
    matches = matches_data.get("results", [])

    results = []
    for m in matches:
        stage = m.get("stage") or {}
        job = m.get("job_position") or m.get("job") or {}
        results.append({
            "email": email,
            "job": job.get("position_name", "") if isinstance(job, dict) else job,
            "stage": stage.get("name", ""),
            "isDropped": not m.get("is_active", True),
        })
    return results


def main():
    headers = build_headers()
    client = OpenAI()

    # Get non-duplicate PDFs
    all_pdfs = sorted(p for p in INPUT_DIR.iterdir() if p.suffix.lower() == ".pdf")
    duplicates = find_duplicates(INPUT_DIR)
    dup_files = set()
    for paths in duplicates.values():
        for p in paths[1:]:
            dup_files.add(p)

    pdfs = [p for p in all_pdfs if p not in dup_files]
    print(f"Total PDFs: {len(all_pdfs)}, non-duplicate: {len(pdfs)}\n")

    found = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name} ... ", end="", flush=True)
        try:
            email = extract_email(client, pdf)
        except Exception as e:
            print(f"ERROR extracting email: {e}")
            continue

        if not email:
            print("no email found")
            continue

        print(f"{email} ... ", end="", flush=True)
        try:
            results = lookup_manatal(headers, email)
        except Exception as e:
            print(f"ERROR Manatal: {e}")
            continue

        if results is None:
            print("not in Manatal")
        else:
            print(f"FOUND ({len(results)} matches)")
            found.extend(results)

    print(f"\n{'='*80}")
    print(f"Candidates found in Manatal: {len(set(r['email'] for r in found))}\n")
    print(f"{'email':<35} {'job':<25} {'stage':<20} {'isDropped'}")
    print("-" * 95)
    for r in found:
        print(f"{r['email']:<35} {str(r['job']):<25} {r['stage']:<20} {r['isDropped']}")


if __name__ == "__main__":
    main()
