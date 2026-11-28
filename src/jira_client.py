"""Client Jira (P1) : issues, transitions, commentaires. API REST v2 via requests.

Mode factice (§8) : si JIRA_BASE_URL est vide, aucune requête n'est envoyée,
l'action est seulement affichée. Le reste du pipeline fonctionne sans Jira.
"""
import itertools
from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth

from src.config import load_config
from src.models import Task

TIMEOUT = 15                    # secondes
COMMENT_MAX = 30000             # Jira refuse les commentaires > 32767 caractères
SUMMARY_MAX = 250               # Jira limite le titre à 255 caractères
ISSUE_TYPE = "Task"
TARGETS = {"in_progress", "done"}

_fake_counter = itertools.count(1)


class JiraError(RuntimeError):
    """Erreur Jira lisible (jamais de token dans le message)."""


def _request(method: str, path: str, **kwargs: Any) -> Any:
    cfg = load_config()
    resp = requests.request(
        method, f"{cfg.jira_base_url}/rest/api/2{path}",
        auth=HTTPBasicAuth(cfg.jira_email, cfg.jira_api_token),
        headers={"Accept": "application/json"},
        timeout=TIMEOUT, **kwargs)
    if resp.status_code >= 400:
        raise JiraError(f"Jira {method} {path} -> {resp.status_code} : {resp.text[:300]}")
    return resp.json() if resp.text else None


def _status_name(target: str) -> str:
    cfg = load_config()
    return cfg.jira_status_in_progress if target == "in_progress" else cfg.jira_status_done


def _current_status(jira_key: str) -> str:
    data = _request("GET", f"/issue/{jira_key}", params={"fields": "status"})
    return data["fields"]["status"]["name"]


def create_issue(task: Task) -> str:
    """Crée l'issue et la met en « En cours ». Renvoie la clé (ex. AGT-12)."""
    cfg = load_config()
    if not cfg.jira_enabled:
        key = f"{cfg.jira_project_key}-FAKE{next(_fake_counter)}"
        print(f"[jira:factice] create_issue {task.task_id} ({task.mode}) -> {key}")
        return key

    summary = f"[{task.task_id}] {task.mode} : {task.description}".replace("\n", " ")
    body = (f"Tâche {task.task_id}\nMode : {task.mode}\nDemande : {task.description}\n"
            f"Branche : {task.branch or '(lecture seule)'}")
    data = _request("POST", "/issue", json={"fields": {
        "project": {"key": cfg.jira_project_key},
        "summary": summary[:SUMMARY_MAX],
        "description": body,
        "issuetype": {"name": ISSUE_TYPE},
    }})
    key = data["key"]
    transition(key, "in_progress")      # no-op si l'issue démarre déjà en « En cours »
    return key


def transition(jira_key: str, target: str) -> None:
    """Déplace l'issue vers target : "in_progress" (En cours) ou "done" (Terminé)."""
    if target not in TARGETS:
        raise ValueError(f"target attendu : {sorted(TARGETS)}, reçu : {target!r}")
    cfg = load_config()
    wanted = _status_name(target)
    if not cfg.jira_enabled:
        print(f"[jira:factice] transition {jira_key} -> {wanted}")
        return

    if _current_status(jira_key).lower() == wanted.lower():
        return                           # déjà dans le bon statut
    available = _request("GET", f"/issue/{jira_key}/transitions")["transitions"]
    for t in available:
        if t["to"]["name"].lower() == wanted.lower():
            _request("POST", f"/issue/{jira_key}/transitions", json={"transition": {"id": t["id"]}})
            return
    names = [t["to"]["name"] for t in available]
    raise JiraError(f"{jira_key} : aucune transition vers « {wanted} » (disponibles : {names})")


def add_comment(jira_key: str, text: str) -> None:
    cfg = load_config()
    if not cfg.jira_enabled:
        print(f"[jira:factice] comment {jira_key} : {text[:80]!r}")
        return
    if len(text) > COMMENT_MAX:
        text = text[:COMMENT_MAX] + "\n[...tronqué]"
    _request("POST", f"/issue/{jira_key}/comment", json={"body": text})


def add_label(jira_key: str, label: str) -> None:
    """Utilisé en cas d'échec : étiquette « agentfailed » (§6.1)."""
    cfg = load_config()
    if not cfg.jira_enabled:
        print(f"[jira:factice] label {jira_key} += {label}")
        return
    _request("PUT", f"/issue/{jira_key}", json={"update": {"labels": [{"add": label}]}})