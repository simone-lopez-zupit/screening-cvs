COMMANDS = [
    {
        "id": "screening_cvs",
        "name": "Screen CVs",
        "script": "screening_cvs.py",
        "inputs": [],
    },
    {
        "id": "find_duplicate_cvs",
        "name": "Find Duplicate CVs",
        "script": "find_duplicate_cvs.py",
        "inputs": [],
    },
    {
        "id": "process_test_results",
        "name": "Process Test Results",
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
    {
        "id": "sync_gmail",
        "name": "Sync Gmail",
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
        "id": "drop_candidates",
        "name": "Drop Candidates",
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
        "id": "export_funnel",
        "name": "Export Funnel",
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
    {
        "id": "check_manatal",
        "name": "Check Manatal",
        "script": "check_manatal.py",
        "inputs": [],
    },
]

COMMANDS_BY_ID = {c["id"]: c for c in COMMANDS}
