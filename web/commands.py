COMMANDS = [
    # ── Group 1: Data sync ────────────────────────
    {
        "id": "sync_gmail",
        "name": "Sync Gmail",
        "icon": "fa-envelope",
        "group": 1,
        "script": "sync_gmail_to_manatal.py",
        "inputs": [
            {
                "name": "BOARD_ORDER",
                "label": "Boards",
                "type": "multi-select",
                "default": ["TL", "DEV"],
                "options": ["TL", "DEV"],
            },
        ],
    },
    {
        "id": "find_duplicate_cvs",
        "name": "Find Duplicate CVs",
        "icon": "fa-copy",
        "group": 1,
        "script": "find_duplicate_cvs.py",
        "inputs": [],
    },
    {
        "id": "check_manatal",
        "name": "Check Manatal",
        "icon": "fa-circle-check",
        "group": 1,
        "script": "check_manatal.py",
        "inputs": [],
    },
    # ── Group 2: Screening pipeline ───────────────
    {
        "id": "screening_cvs",
        "name": "Screen CVs",
        "icon": "fa-file-lines",
        "group": 2,
        "script": "screening_cvs.py",
        "inputs": [],
    },
    {
        "id": "drop_candidates",
        "name": "Drop Candidates",
        "icon": "fa-user-xmark",
        "group": 2,
        "script": "drop_candidates.py",
        "inputs": [
            {
                "name": "DROP_DEV",
                "label": "Drop DEV",
                "type": "bool",
                "default": True,
            },
            {
                "name": "DROP_TL",
                "label": "Drop TL",
                "type": "bool",
                "default": False,
            },
        ],
    },
    {
        "id": "drop_from_board",
        "name": "Drop from Board",
        "icon": "fa-arrow-right-from-bracket",
        "group": 2,
        "script": "drop_from_board.py",
        "inputs": [
            {
                "name": "SOURCE_JOB_ID",
                "label": "Source Job ID",
                "type": "text",
                "default": "3301964",
            },
            {
                "name": "TARGET_JOB_ID",
                "label": "Target Job ID",
                "type": "text",
                "default": "303943",
            },
            {
                "name": "STAGE_NAME",
                "label": "Stage Name",
                "type": "text",
                "default": "Da droppare",
            },
        ],
    },
    {
        "id": "send_google_form",
        "name": "Send Google Form",
        "icon": "fa-paper-plane",
        "group": 2,
        "script": "send_google_form_test.py",
        "inputs": [],
    },
    {
        "id": "process_test_results",
        "name": "Process Test Results",
        "icon": "fa-clipboard-check",
        "group": 2,
        "script": "process_test_results.py",
        "inputs": [
            {
                "name": "NON_FARE_COSE",
                "label": "Dry run",
                "type": "bool",
                "default": True,
            },
            {
                "name": "BOARD_ORDER",
                "label": "Boards",
                "type": "multi-select",
                "default": ["DEV", "TL"],
                "options": ["DEV", "TL"],
            },
        ],
    },
    # ── Group 3: Reporting ────────────────────────
    {
        "id": "export_funnel",
        "name": "Export Funnel",
        "icon": "fa-chart-funnel",
        "group": 3,
        "script": "export_funnel_stats.py",
        "inputs": [
            {
                "name": "BOARD",
                "label": "Board",
                "type": "select",
                "default": "DEV",
                "options": ["DEV", "TL"],
            },
        ],
    },
]

COMMANDS_BY_ID = {c["id"]: c for c in COMMANDS}
