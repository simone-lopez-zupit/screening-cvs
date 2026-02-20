# Screening CVs

Recruitment automation toolkit that integrates **Manatal** (ATS), **Gmail**, **TestDome**, and **OpenAI GPT-4o** to streamline the candidate screening pipeline.

## Scripts

### `screening_cvs.py`

Parses CV PDFs using GPT-4o, extracts structured candidate data, evaluates acceptance criteria, and exports results to Excel. Also produces zip archives of accepted/rejected CVs.

**What it does:**
- Detects and moves duplicate PDFs before processing
- Sends each PDF to GPT-4o to extract: name, position, location, contacts, LinkedIn/GitHub, personal projects, and years of experience
- Evaluates 4 conditions (age, bootcamp attendance, consulting company tenure, Italian language level) to decide ACCETTATO/RIFIUTATO
- Cross-references candidates on Manatal by email
- Outputs a color-coded Excel file and two zip archives (approved / rejected)

**Usage:**
```bash
python screening_cvs.py --input-dir cvs --model gpt-4o --limit 10 --pause 1.0
```

---

### `process_test_results.py`

Processes TestDome test results and matches them against candidates in a Manatal pipeline stage. Based on scores, it can move candidates forward, drop them, or flag them for manual review.

**What it does:**
- Fetches all test results from the TestDome API
- Fetches candidates from a Manatal pipeline stage ("Test preliminare")
- Matches candidates by email and evaluates scores:
  - Score >= 80: moves candidate to "Chiacchierata conoscitiva" and sends an invitation email
  - Score < 60: drops the candidate and sends a rejection email
  - Score 60-79: flagged for manual evaluation
- Creates Testdome notes on Manatal candidate profiles
- Has a `NON_FARE_COSE` dry-run flag to preview actions without executing them

**Usage:**
```bash
python process_test_results.py --email-drop-body-file path/to/drop.txt --email-chiacchierata-body-file path/to/invite.txt
```

---

### `send_google_form_test.py`

Sends templated emails (e.g. test invitations) to candidates in a specific Manatal pipeline stage and optionally moves them to the next stage.

**What it does:**
- Fetches candidates from a configurable pipeline stage (default: "Test preliminare (TL)")
- Sends a templated email to each candidate using Gmail
- Can move candidates to the next pipeline stage (currently commented out)
- Configurable sleep between emails to avoid rate limits

**Usage:**
```bash
python send_google_form_test.py
```

---

### `drop_candidates.py`

Drops (rejects) all candidates in a given Manatal pipeline stage and sends them a rejection email.

**What it does:**
- Supports multiple boards (TL / DEV) via the `BOARDS` config
- Fetches all candidates from the configured stage (e.g. "Nuova candidatura (TL)" or "Test preliminare")
- Drops each candidate on Manatal
- Sends a templated rejection email via Gmail
- Configurable sleep between operations

**Usage:**
```bash
python drop_candidates.py
```
Change the `BOARD` variable at the top of the file to switch between TL and DEV.

---

### `export_funnel_stats.py`

Exports recruitment funnel statistics to Excel, grouped by pipeline stage and broken down by configurable date ranges.

**What it does:**
- Fetches all matches for a job from Manatal
- Groups candidates by pipeline stage and computes per-stage metrics: dropped, standing, passed, total, pass rate, drop rate, cumulative drop rate
- Outputs stats for multiple date ranges (yearly, monthly, custom periods) into a single Excel file

**Usage:**
```bash
python export_funnel_stats.py
```

---

### `sync_gmail_to_manatal.py`

Syncs recruitment email content from Gmail into Manatal candidate notes, so recruiters have the application email body visible directly on the candidate profile.

**What it does:**
- Fetches candidates across all pipeline stages for a given job board (TL / DEV)
- For each candidate, searches Gmail for their recruitment application email
- Creates a note on the Manatal candidate profile with the email body
- Skips candidates that already have a synced note
- Supports dry-run mode (`DRY_RUN=true`), note limit (`LIMIT=N`), and saving results to a JSON file (`SAVE_FILE=path`)

**Usage:**
```bash
python sync_gmail_to_manatal.py

# Dry run
DRY_RUN=true python sync_gmail_to_manatal.py

# Save to file instead of creating notes
SAVE_FILE=output.json python sync_gmail_to_manatal.py
```

## External Services

| Service    | Purpose                                  |
|------------|------------------------------------------|
| **Manatal**  | ATS — candidate management, pipeline stages, notes |
| **Gmail**    | Send templated emails, search recruitment emails   |
| **TestDome** | Fetch candidate test scores and results            |
| **OpenAI**   | GPT-4o for CV PDF parsing and evaluation           |

## Configuration

All scripts use environment variables loaded from a `.env` file. Key variables:

- `MANATAL_API_KEY` — Manatal API key
- `MANATAL_JOB_DEV_ID` / `MANATAL_JOB_TL_ID` — Job IDs for DEV and TL boards
- `TEST_DOME_CLIENT_ID` / `TEST_DOME_CLIENT_SECRET` — TestDome API credentials
- `OPENAI_API_KEY` — OpenAI API key
- `DROP_EMAIL_BODY_FILE` — Path to rejection email template
- `SEND_TEST_EMAIL_BODY_FILE` — Path to test invitation email template
- `SEND_CHIACCHIERATA_EMAIL_BODY_FILE` — Path to interview invitation email template
