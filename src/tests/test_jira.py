
import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

BASE_URL = os.getenv("JIRA_BASE_URL")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

auth = HTTPBasicAuth(EMAIL, API_TOKEN)

headers = {
    "Accept": "application/json"
}

# 1. Vérifier l'authentification
response = requests.get(
    f"{BASE_URL}/rest/api/2/myself",
    headers=headers,
    auth=auth
)

if response.status_code == 200:
    print("Connexion Jira réussie !")
    print("Status HTTP :", response.status_code)
    print("Content-Type :", response.headers.get("Content-Type"))
    print("Réponse Jira :")
    print(response.text)
    if response.status_code == 200:
        data = response.json()
        print("Compte :", data.get("displayName"))
    else:
        print("Erreur Jira :", response.status_code)
else:
    print("Erreur d'authentification :", response.status_code)
    print(response.text)
    exit()

# 2. Vérifier le projet
response = requests.get(
    f"{BASE_URL}/rest/api/2/project/{PROJECT_KEY}",
    headers=headers,
    auth=auth
)

if response.status_code == 200:
    project = response.json()
    print("Projet trouvé :", project["name"])
    print("Clé :", project["key"])
else:
    print("Erreur projet :", response.status_code)
    print(response.text)
