# scripts/check_jira.py
import os
import sys

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()


def main() -> int:
    base = os.getenv("JIRA_BASE_URL")
    key = os.getenv("JIRA_PROJECT_KEY")
    if not base or not os.getenv("JIRA_EMAIL") or not os.getenv("JIRA_API_TOKEN"):
        print("Variables JIRA_* manquantes dans .env")
        return 1

    auth = HTTPBasicAuth(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])
    headers = {"Accept": "application/json"}

    r = requests.get(f"{base}/rest/api/2/myself", headers=headers, auth=auth)
    if r.status_code != 200:
        print("Auth échouée :", r.status_code, r.text)
        return 1
    print("Compte :", r.json().get("displayName"))

    r = requests.get(f"{base}/rest/api/2/project/{key}", headers=headers, auth=auth)
    if r.status_code != 200:
        print("Projet introuvable :", r.status_code, r.text)
        return 1
    print("Projet :", r.json()["name"], f"({r.json()['key']})")

    # Statuts disponibles dans le workflow du projet
    r = requests.get(f"{base}/rest/api/2/project/{key}/statuses", headers=headers, auth=auth)
    if r.status_code == 200:
        for issue_type in r.json():
            names = [s["name"] for s in issue_type["statuses"]]
            print(f"Statuts pour {issue_type['name']} :", names)
    return 0


if __name__ == "__main__":
    sys.exit(main())