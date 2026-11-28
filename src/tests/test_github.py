import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")

url = f"https://api.github.com/repos/{REPO}"

response = requests.get(
    url,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json"
    }
)

print("Status HTTP :", response.status_code)

if response.status_code == 200:
    data = response.json()
    print("Connexion GitHub réussie !")
    print("Repository :", data["full_name"])
    print("Branche par défaut :", data["default_branch"])
else:
    print("Erreur :", response.text)