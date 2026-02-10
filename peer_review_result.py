import gspread
from google.oauth2 import service_account


PEOPLE = {
    "Alberto Tavoletti": {"role": "dev", "email": "alberto.tavoletti@zupit.it"},
    "Alessandro Richetto": {"role": "dev", "email": "alessandro.richetto@zupit.it"},
    "Alessandro Saiani": {"role": "tl", "email": "alessandro.saiani@zupit.it"},
    "Andrea Demattè": {"role": "tl", "email": "andrea.demattè@zupit.it"},
    "Armando Capozza": {"role": "dev", "email": "armando.capozza@zupit.it"},
    "Boris Sclauzero": {"role": "tl", "email": "boris.sclauzero@zupit.it"},
    "Brando Caserotti": {"role": "dev", "email": "brando.caserotti@zupit.it"},
    "Camilla Pacifici": {"role": "po", "email": "camilla.pacifici@zupit.it"},
    "Claudio Bizzotto": {"role": "dev", "email": "claudio.bizzotto@zupit.it"},
    "Daniel Lauri": {"role": "dev", "email": "daniel.lauri@zupit.it"},
    "Davide Bontempelli": {"role": "dev", "email": "davide.bontempelli@zupit.it"},
    "Davide Michelon": {"role": "dev", "email": "davide.michelon@zupit.it"},
    "Dennis Avesani": {"role": "dev", "email": "dennis.avesani@zupit.it"},
    "Deyan Koba": {"role": "dev", "email": "deyan.koba@zupit.it"},
    "Francesca Pittalis": {"role": "po", "email": "francesca.pittalis@zupit.it"},
    "Francesco Carusi": {"role": "dev", "email": "francesco.carusi@zupit.it"},
    "Francesco Mesuraca": {"role": "dev", "email": "francesco.mesuraca@zupit.it"},
    "Giacomo Cavicchioli": {"role": "dev", "email": "giacomo.cavicchioli@zupit.it"},
    "Giorgio Betta": {"role": "dev", "email": "giorgio.betta@zupit.it"},
    "Giorgio Visentin": {"role": "dev", "email": "giorgio.visentin@zupit.it"},
    "Giorgio Zanoni": {"role": "po", "email": "giorgio.zanoni@zupit.it"},
    "Giovanni Pepe": {"role": "tl", "email": "giovanni.pepe@zupit.it"},
    "Giovanni Zanibellato": {"role": "dev", "email": "giovanni.zanibellato@zupit.it"},
    "Giuliano Abruzzo": {"role": "dev", "email": "giuliano.abruzzo@zupit.it"},
    "Ivan Morandi": {"role": "dev", "email": "ivan.morandi@zupit.it"},
    "Jens Smeds": {"role": "dev", "email": "jens.smeds@zupit.it"},
    "Lorenzo Rivaroli": {"role": "po", "email": "lorenzo.rivaroli@zupit.it"},
    "Luca Erculiani": {"role": "tl", "email": "luca.erculiani@zupit.it"},
    "Luca Sartori": {"role": "dev", "email": "luca.sartori@zupit.it"},
    "Marco Bacis": {"role": "dev", "email": "marco.bacis@zupit.it"},
    "Mario De Donno": {"role": "tl", "email": "mario.de.donno@zupit.it"},
    "Martin Perosa": {"role": "dev", "email": "martin.perosa@zupit.it"},
    "Massimo Telch": {"role": "tl", "email": "massimo.telch@zupit.it"},
    "Matteo Taverna": {"role": "po", "email": "matteo.taverna@zupit.it"},
    "Michele Puricelli": {"role": "dev", "email": "michele.puricelli@zupit.it"},
    "Michele Segata": {"role": "dev", "email": "michele.segata@zupit.it"},
    "Nicholas Zanardi": {"role": "dev", "email": "nicholas.zanardi@zupit.it"},
    "Paolo Dadda": {"role": "dev", "email": "paolo.dadda@zupit.it"},
    "Pietro De Vigili": {"role": "po", "email": "pietro.devigili@zupit.it"},
    "Roberto Demozzi": {"role": "dev", "email": "roberto.demozzi@zupit.it"},
    "Roberto Passatempi": {"role": "po", "email": "roberto.passatempi@zupit.it"},
    "Rossana Bartolacelli": {"role": "po", "email": "rossana.bartolacelli@zupit.it"},
    "Simonpaolo Lopez": {"role": "dev", "email": "simonpaolo.lopez@zupit.it"},
    "Thomas Borgogno": {"role": "dev", "email": "thomas.borgogno@zupit.it"},
    "Valentino Cioffi": {"role": "dev", "email": "valentino.cioffi@zupit.it"},
}

PEOPLE = {
    "Lorenzo Rivaroli": {"role": "po", "email": "lorenzo.30000@gmail.com"},
}

# ==== SCRIPT (non toccare) ====
def build_file_title(nome: str) -> str:
    return f"{nome} - Peer review - result"

SERVICE_ACCOUNT_FILE = "google-credentials.json"
TEMPLATE_SPREADSHEET_ID = "1L1z9NEBcv48ac9Monj9cFZQINkzkVhXMuetaEC2GqW4"
DESTINATION_FOLDER_ID = "1SM74i01YyOff_ErFLKiJQacns62FGvrS"

IMPERSONATE_USER = "lorenzo.rivaroli@zupit.it"


scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=scopes
)

delegated_credentials = credentials.with_subject(IMPERSONATE_USER)
gc = gspread.authorize(delegated_credentials)

for name, data in PEOPLE.items():
    try:
        role = data["role"]
        email = data["email"]

        new_sheet = gc.copy(
            TEMPLATE_SPREADSHEET_ID,
            build_file_title(name),
            folder_id=DESTINATION_FOLDER_ID
        )

        new_sheet.sheet1.update("A1", name)
        new_sheet.share(email, perm_type="user", role="reader")

        print(f"✅ {name} ({role}) → {email}")
    except Exception as e:
        print(f"❌ {name}: {e}\n")
