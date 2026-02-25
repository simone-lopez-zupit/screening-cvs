BOARD_INPUTS = [
    {
        "name": "BOARD_DEV",
        "label": "Board DEV",
        "type": "bool",
        "default": True,
    },
    {
        "name": "BOARD_TL",
        "label": "Board TL",
        "type": "bool",
        "default": True,
    },
]

COMMANDS = [
    # ── Group 1: Data sync ────────────────────────
    {
        "id": "sync_gmail",
        "name": "Sync Gmail",
        "icon": "fa-envelope",
        "description": "Cerca nelle email Gmail i dati delle candidature e li sincronizza come note sui candidati in Manatal.",
        "group": 1,
        "script": "sync_gmail_to_manatal.py",
        "inputs": list(BOARD_INPUTS),
    },
    {
        "id": "find_duplicate_cvs",
        "name": "Find Duplicate CVs",
        "icon": "fa-copy",
        "description": "Confronta i CV tra le cartelle per individuare duplicati tramite hash dei file.",
        "group": 1,
        "script": "find_duplicate_cvs.py",
        "inputs": [],
    },
    {
        "id": "check_manatal",
        "name": "Check Manatal",
        "icon": "fa-circle-check",
        "description": "Verifica la connessione e lo stato dell'API Manatal.",
        "group": 1,
        "script": "check_manatal.py",
        "inputs": [],
    },
    # ── Group 2: Screening pipeline ───────────────
    {
        "id": "screening_cvs",
        "name": "Screen CVs",
        "icon": "fa-file-lines",
        "description": "Analizza i CV dei candidati e li valuta per lo screening iniziale.",
        "group": 2,
        "script": "screening_cvs.py",
        "inputs": [],
    },
    {
        "id": "drop_candidates",
        "name": "Drop Candidates",
        "icon": "fa-user-xmark",
        "description": "Scarta i candidati non idonei e invia loro l'email di notifica.",
        "group": 2,
        "script": "drop_candidates.py",
        "inputs": list(BOARD_INPUTS) + [
            {
                "name": "STAGE_NAME",
                "label": "Stage name",
                "type": "text",
                "default": "nuova_candidatura",
            },
        ],
    },
    {
        "id": "send_google_form",
        "name": "Send Google Form",
        "icon": "fa-paper-plane",
        "description": "Invia ai candidati il link al Google Form per la scelta delle tecnologie del test tecnico.",
        "group": 2,
        "script": "send_google_form_test.py",
        "inputs": [],
    },
    {
        "id": "process_test_results",
        "name": "Process Test Results",
        "icon": "fa-clipboard-check",
        "description": "Elabora i risultati dei test Testdome: promuove o scarta i candidati e invia le email corrispondenti.",
        "group": 2,
        "script": "process_test_results.py",
        "inputs": [
            {
                "name": "NON_FARE_COSE",
                "label": "Dry run",
                "type": "bool",
                "default": True,
            },
        ] + list(BOARD_INPUTS),
    },
    # ── Group 3: Reporting ────────────────────────
    {
        "id": "export_funnel",
        "name": "Export Funnel",
        "icon": "fa-chart-funnel",
        "description": "Esporta le statistiche del funnel di selezione in un file Excel.",
        "group": 3,
        "script": "export_funnel_stats.py",
        "inputs": list(BOARD_INPUTS),
    },
]

COMMANDS_BY_ID = {c["id"]: c for c in COMMANDS}
