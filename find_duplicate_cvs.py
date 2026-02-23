"""
Trova CV (PDF) della stessa persona inviati in più sottocartelle.
Confronta per email estratta dal CV (via OpenAI) e per hash del file.
Uso: python find_duplicate_cvs.py <cartella_padre>
"""

import base64
import json
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from services.file_utils import hash_file

load_dotenv()

EMAIL_PROMPT = (
    "Estrai SOLO l'indirizzo email dal CV allegato.\n"
    "Rispondi con un JSON: {\"email\": \"...\"}\n"
    "Se non trovi un'email, rispondi: {\"email\": null}"
)


def extract_email(client: OpenAI, pdf_path: Path) -> str | None:
    with pdf_path.open("rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": pdf_path.name,
                            "file_data": f"data:application/pdf;base64,{b64}",
                        },
                    },
                    {"type": "text", "text": EMAIL_PROMPT},
                ],
            }
        ],
    )

    data = json.loads(resp.choices[0].message.content)
    email = data.get("email")
    return email.strip().lower() if email else None


def find_duplicates_by_email(parent: Path) -> dict[str, list[Path]]:
    """Return email -> list of PDF paths that share the same email across subfolders."""
    client = OpenAI()
    emails: dict[str, list[Path]] = defaultdict(list)

    pdfs = []
    for subfolder in sorted(parent.iterdir()):
        if not subfolder.is_dir():
            continue
        pdfs.extend(sorted(subfolder.glob("*.pdf")))

    for i, pdf in enumerate(pdfs, 1):
        print(f"  [{i}/{len(pdfs)}] {pdf.parent.name}/{pdf.name} ... ", end="", flush=True)
        try:
            email = extract_email(client, pdf)
        except Exception as e:
            print(f"errore: {e}")
            continue
        if email:
            print(email)
            emails[email].append(pdf)
        else:
            print("nessuna email")

    return {
        email: paths
        for email, paths in emails.items()
        if len({p.parent for p in paths}) > 1
    }


def find_duplicates_by_hash(parent: Path) -> dict[str, list[Path]]:
    """Return hash -> list of PDF paths that appear in more than one subfolder."""
    hashes: dict[str, list[Path]] = defaultdict(list)
    for subfolder in sorted(parent.iterdir()):
        if not subfolder.is_dir():
            continue
        for pdf in sorted(subfolder.glob("*.pdf")):
            hashes[hash_file(pdf)].append(pdf)

    return {
        h: paths
        for h, paths in hashes.items()
        if len({p.parent for p in paths}) > 1
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Uso: python {Path(__file__).name} <cartella_padre>")
        sys.exit(1)

    parent = Path(sys.argv[1])
    if not parent.is_dir():
        print(f"Errore: '{parent}' non è una cartella valida.")
        sys.exit(1)

    # --- Duplicati per file identico (hash) ---
    hash_dups = find_duplicates_by_hash(parent)
    if hash_dups:
        print(f"\n=== {len(hash_dups)} CV identici (stesso file) in più cartelle ===\n")
        for paths in hash_dups.values():
            print(f"  {paths[0].name}")
            for p in paths:
                print(f"    - {p.parent.name}")
            print()

    # --- Duplicati per email (stessa persona, CV diverso) ---
    print("\nEstrazione email dai CV...\n")
    email_dups = find_duplicates_by_email(parent)
    if email_dups:
        print(f"\n=== {len(email_dups)} persone con CV in più cartelle (stessa email) ===\n")
        for email, paths in email_dups.items():
            print(f"  {email}")
            for p in paths:
                print(f"    - {p.parent.name}/{p.name}")
            print()

    if not hash_dups and not email_dups:
        print("\nNessun CV duplicato trovato tra le sottocartelle.")


if __name__ == "__main__":
    main()
