import os

BOARDS = {
    "TL": {
        "job_id": os.getenv("MANATAL_JOB_TL_ID"),
        "stages": {
            "nuova_candidatura": "Nuova candidatura (TL)",
            "interessante": "Interessante - per futuro (TL)",
            "test_preliminare": "Test preliminare (TL)",
            "chiacchierata": "Chiacchierata conoscitiva (TL)",
            "feedback_chiacchierata": "Feedback chiacchierata conoscitiva (TL)",
            "colloquio_tecnico": "Colloquio tecnico (TL)",
            "test_pratico": "Test pratico chiacchierata con FD (TL)",
            "approfondimenti": "Approfondimenti (TL)",
            "proposta": "Proposta (TL)",
        },
    },
    "DEV": {
        "job_id": os.getenv("MANATAL_JOB_DEV_ID"),
        "stages": {
            "nuova_candidatura": "Nuova candidatura",
            "interessante": "Interessante - per futuro",
            "test_preliminare": "Test preliminare",
            "chiacchierata": "Chiacchierata conoscitiva",
            "feedback_chiacchierata": "Feedback chiacchierata conoscitiva",
            "colloquio_tecnico": "Colloquio tecnico",
            "live_coding": "Live coding",
        },
    },
}
