"""
Estrae informazioni strutturate dai PDF dei CV, salva i risultati in Excel
e organizza zip dei CV accettati/rifiutati usando GPT-4o per il parsing.
"""

import base64
import hashlib
import json
import os
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import PatternFill
from openai import OpenAI
from dotenv import load_dotenv

from services.manatal_service import build_headers, get_candidate_info


load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────
INPUT_DIR = "cvs"
DUPLICATES_DIR = "cvs_duplicati"
MODEL = "gpt-4o"
PAUSE = 0.0
LIMIT = None
# ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Sei un assistente che esegue OCR e parsing di CV. "
    "Analizza il PDF allegato e restituisci SOLO un oggetto JSON conforme allo schema richiesto. "
    "Estrai solo i fatti, non valutare. Non aggiungere testo fuori dal JSON."
)

USER_PROMPT = (
    "Estrai informazioni strutturate dal CV.\n"
    "\n"
    "INFORMAZIONI DA ESTRARRE:\n"
    "- Nome completo della persona\n"
    "- Posizione lavorativa attuale\n"
    "- Luogo di residenza / città\n"
    "- Email\n"
    "- Telefono\n"
    "- Link LinkedIn (se presente)\n"
    "- Link GitHub (se presente)\n"
    "- Progetti personali extra-lavorativi citati nel CV (se presenti)\n"
    "- Esperienze lavorative o formative in settori diversi dallo sviluppo software (se presenti)\n"
    "- Se ha almeno 3 anni di esperienza fullstack nello sviluppo web\n"
    "- Anno di nascita (se presente o deducibile)\n"
    "- Lingua in cui è scritto il CV\n"
    "- Lingue conosciute con livello (madrelingua, A1, A2, B1, B2, C1, C2)\n"
    "- Percorso di formazione: lista di istituti/scuole/bootcamp con tipo (università, bootcamp, corso online, ecc.)\n"
    "- Esperienze lavorative: lista di aziende con anni di permanenza\n"
    "Se un dato non é ricavabile lascia la stringa vuota o null.\n"
    "\n"
    "Restituisci un oggetto JSON con questa struttura:\n"
    "{\n"
    '  "full_name": "",\n'
    '  "current_position": "",\n'
    '  "location": "",\n'
    '  "email": "",\n'
    '  "phone": "",\n'
    '  "linkedin": "",\n'
    '  "github": "",\n'
    '  "personal_projects": "",\n'
    '  "extra_tech": "",\n'
    '  "3y_exp_web": "",\n'
    '  "birth_year": null,\n'
    '  "cv_language": "",\n'
    '  "languages": [{"language": "", "level": ""}],\n'
    '  "education": [{"institution": "", "type": ""}],\n'
    '  "work_experiences": [{"company": "", "years": 0.0}]\n'
    "}\n"
    "NON inventare informazioni. Estrai solo ciò che è presente nel CV."
)


def call_model_with_pdf_file(client: OpenAI, pdf_path: Path, model: str) -> Dict[str, str]:
    """
    Legge il PDF, lo codifica in base64 e lo passa al modello
    tramite Chat Completions API usando il tipo di contenuto 'file'.
    Il modello é forzato a rispondere in JSON tramite response_format.
    """
    # sono riuscito a mandarlo solo in base64 vabbu
    with pdf_path.open("rb") as f:
        pdf_bytes = f.read()
    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "file",
                    "file": {
                        "filename": pdf_path.name,
                        "file_data": f"data:application/pdf;base64,{base64_pdf}",
                    },
                },
                {
                    "type": "text",
                    "text": USER_PROMPT,
                },
            ],
        },
    ]

    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=messages,
    )

    content = completion.choices[0].message.content

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Risposta non JSON dal modello: {e}; content={content!r}") from e


CONDITION_KEYS = ["eta", "boolean", "accenture", "italiano"]

BOOTCAMP_NAMES = {
    "boolean careers", "boolean", "epicode", "42 school", "42",
    "start2impact", "develhope", "aulab", "ironhack", "le wagon",
}

CONSULTING_FIRMS = {
    "almaviva", "almawave", "reply", "accenture", "deloitte", "kpmg",
    "engineering", "dxc", "ntt data", "capgemini", "everis", "sogeti",
}


def evaluate_eta(raw: Dict[str, Any]) -> tuple:
    """Età: FALSE se > 45 anni, TRUE se <= 45, NULL se non determinabile."""
    birth_year = raw.get("birth_year")
    if birth_year is None:
        return "NULL", "Anno di nascita non presente nel CV."
    try:
        birth_year = int(birth_year)
    except (ValueError, TypeError):
        return "NULL", f"Anno di nascita non valido: {birth_year}"
    current_year = datetime.now().year
    age = current_year - birth_year
    if age > 45:
        return "FALSE", f"Nato nel {birth_year}, età stimata {age} (> 45)."
    return "TRUE", f"Nato nel {birth_year}, età stimata {age} (<= 45)."


def evaluate_boolean(raw: Dict[str, Any]) -> tuple:
    """Boolean: FALSE se ha frequentato un bootcamp noto, TRUE altrimenti."""
    education = raw.get("education") or []
    for entry in education:
        institution = (str(entry.get("institution", "")) or "").strip().lower()
        for bootcamp in BOOTCAMP_NAMES:
            if bootcamp in institution:
                return "FALSE", f"Ha frequentato il bootcamp: {entry.get('institution')}."
    return "TRUE", "Nessun bootcamp noto trovato nel percorso formativo."


def evaluate_accenture(raw: Dict[str, Any]) -> tuple:
    """Accenture: FALSE se > 5 anni complessivi in società di consulenza IT."""
    work_experiences = raw.get("work_experiences") or []
    total_years = 0.0
    matched_companies = []
    for entry in work_experiences:
        company = (str(entry.get("company", "")) or "").strip().lower()
        for firm in CONSULTING_FIRMS:
            if firm in company:
                years = 0.0
                try:
                    years = float(entry.get("years", 0) or 0)
                except (ValueError, TypeError):
                    pass
                total_years += years
                matched_companies.append(f"{entry.get('company')} ({years}a)")
                break
    if total_years > 5:
        return "FALSE", f"Totale {total_years} anni in consulenza IT: {', '.join(matched_companies)}."
    if matched_companies:
        return "TRUE", f"Totale {total_years} anni in consulenza IT (<= 5): {', '.join(matched_companies)}."
    return "TRUE", "Nessuna esperienza in società di consulenza IT note."


def evaluate_italiano(raw: Dict[str, Any]) -> tuple:
    """Italiano: TRUE se parla italiano madrelingua/C1/C2 o CV scritto in italiano."""
    cv_language = (str(raw.get("cv_language", "")) or "").strip().lower()
    if cv_language in ("italiano", "italian", "it"):
        return "TRUE", "Il CV è scritto in italiano."

    languages = raw.get("languages") or []
    for entry in languages:
        lang = (str(entry.get("language", "")) or "").strip().lower()
        level = (str(entry.get("level", "")) or "").strip().lower()
        if lang in ("italiano", "italian", "it"):
            if any(kw in level for kw in ("madrelingua", "nativo", "native", "c1", "c2")):
                return "TRUE", f"Italiano dichiarato a livello: {entry.get('level')}."
            return "FALSE", f"Italiano dichiarato a livello: {entry.get('level')} (inferiore a C1)."

    return "FALSE", "Italiano non menzionato e CV non in italiano."


def hash_file(path: Path, chunk_size: int = 1_048_576) -> str:
    """Calcola SHA-256 del file leggendo a chunk."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(input_dir: Path) -> Dict[str, List[Path]]:
    """Restituisce una mappa hash -> lista di file con lo stesso hash (solo duplicati)."""
    hashes: Dict[str, List[Path]] = {}
    for pdf_path in sorted(input_dir.iterdir()):
        if pdf_path.suffix.lower() != ".pdf":
            continue
        file_hash = hash_file(pdf_path)
        hashes.setdefault(file_hash, []).append(pdf_path)
    return {h: paths for h, paths in hashes.items() if len(paths) > 1}


def _unique_destination(dest_dir: Path, original_name: str) -> Path:
    """Trova un nome unico nella cartella di destinazione."""
    dest = dest_dir / original_name
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    counter = 1
    while True:
        candidate = dest_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_duplicates(duplicates: Dict[str, List[Path]], target_dir: Path) -> None:
    """Sposta tutti i duplicati (tranne il primo di ogni gruppo) nella cartella target."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for paths in duplicates.values():
        # Mantieni il primo file in origine, sposta gli altri
        for pdf_path in paths[1:]:
            destination = _unique_destination(target_dir, pdf_path.name)
            shutil.move(str(pdf_path), destination)


EVALUATE_FUNCTIONS = {
    "eta": evaluate_eta,
    "boolean": evaluate_boolean,
    "accenture": evaluate_accenture,
    "italiano": evaluate_italiano,
}


def sanitize_fields(raw: Dict[str, Any]) -> Dict[str, str]:
    """Normalizza i campi attesi, valuta condizioni in Python e determina decisione."""
    fields = ["full_name", "current_position", "location", "email", "phone", "linkedin", "github", "personal_projects", "extra_tech", "3y_exp_web"]
    cleaned: Dict[str, str] = {field: (str(raw.get(field, "")) or "").strip() for field in fields}

    condition_values = []
    for key in CONDITION_KEYS:
        evaluate_fn = EVALUATE_FUNCTIONS[key]
        value, explanation = evaluate_fn(raw)
        cleaned[f"{key}_value"] = value
        cleaned[f"{key}_explanation"] = explanation
        condition_values.append(value)

    cleaned["decision"] = "RIFIUTATO" if "FALSE" in condition_values else "ACCETTATO"
    return cleaned


OUTPUT_FIELDS = [
    "file_name",
    "full_name",
    "current_position",
    "location",
    "email",
    "phone",
    "linkedin",
    "github",
    "personal_projects",
    "extra_tech",
    "3y_exp_web",
    "eta_value",
    "eta_explanation",
    "boolean_value",
    "boolean_explanation",
    "accenture_value",
    "accenture_explanation",
    "italiano_value",
    "italiano_explanation",
    "decision",
    "manatal_link",
    "note",
]


def write_rows_to_excel(rows: List[Dict[str, str]], output_path: Path, headers: List[str]) -> None:
    """Salva le righe su un file Excel applicando il colore sulla decisione."""
    wb = Workbook()
    ws = wb.active
    ws.title = "CV"
    ws.append(headers)

    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    print(f"Excel rows number: {len(rows)}\n")
    for row in rows:
        ws.append([row.get(field, "") for field in headers])
        current_row = ws.max_row
        decision_value = (row.get("decision") or "").upper()
        fill = green_fill if decision_value == "ACCETTATO" else red_fill if decision_value == "RIFIUTATO" else None
        if fill:
            for cell in ws[current_row]:
                cell.fill = fill

    wb.save(output_path)


def create_zip(zip_path: Path, files: List[Path]) -> None:
    """Crea uno zip contenente i file indicati; ignora i file mancanti."""
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            if file_path.exists():
                zf.write(file_path, arcname=file_path.name)


def process_directory(
    headers: Dict[str, str],
    input_dir: Path,
    model: str,
    pause: float,
    limit: Optional[int],
) -> List[Dict[str, str]]:
    files = sorted(p for p in input_dir.iterdir() if p.suffix.lower() == ".pdf")
    if limit is not None:
        files = files[:limit]

    client = OpenAI()
    rows: List[Dict[str, str]] = []
    for idx, pdf_path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Lavoro su: {pdf_path.name}")
        note = ""

        raw = {}
        try:
            raw = call_model_with_pdf_file(client, pdf_path, model)
            data = sanitize_fields(raw)
        except Exception as exc:  # noqa: BLE001
            note = f"errore: {exc}"
            data = sanitize_fields({})

        cand_email = raw.get("email")
        if cand_email:
            manatal_link, manatal_matches = get_candidate_info(headers, cand_email)
        else:
            manatal_link, manatal_matches = "", ""

        row = {"file_name": pdf_path.name, **data, "manatal_link": manatal_link, "note": note}
        rows.append(row)

        if pause > 0 and idx < len(files):
            time.sleep(pause)

    return rows


def main() -> None:
    input_dir = Path(INPUT_DIR)
    duplicates_dir = Path(DUPLICATES_DIR)

    headers = build_headers()

    if not input_dir.is_dir():
        raise SystemExit(f"Cartella di input non trovata: {input_dir}")
    duplicates = find_duplicates(input_dir)
    if duplicates:
        print("Duplicati trovati (hash -> file):")
        for file_hash, paths in duplicates.items():
            print(f"\n{file_hash}:")
            for p in paths:
                print(f"  - {p.name}")
        move_duplicates(duplicates, duplicates_dir)
        print(f"\nDuplicati spostati in: {duplicates_dir}")
    else:
        print("Nessun duplicato trovato.")

    rows = process_directory(
        headers=headers,
        input_dir=input_dir,
        model=MODEL,
        pause=PAUSE,
        limit=LIMIT
    )

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    excel_path = Path(f"cv_{timestamp_str}.xlsx")
    write_rows_to_excel(rows, output_path=excel_path, headers=OUTPUT_FIELDS)
    print(f"Excel salvato in: {excel_path}")

    accepted_files: List[Path] = []
    rejected_files: List[Path] = []

    for row in rows:
        decision = (row.get("decision") or "").upper()
        pdf_path = input_dir / row.get("file_name", "")
        if decision == "ACCETTATO":
            accepted_files.append(pdf_path)
        elif decision == "RIFIUTATO":
            rejected_files.append(pdf_path)

    zip_accept_path = Path(f"cv_approvati_{timestamp_str}.zip")
    zip_reject_path = Path(f"cv_rifiutati_{timestamp_str}.zip")
    create_zip(zip_accept_path, accepted_files)
    create_zip(zip_reject_path, rejected_files)
    print(f"Zip ACCETTATI: {zip_accept_path}")
    print(f"Zip RIFIUTATI: {zip_reject_path}")


if __name__ == "__main__":
    main()