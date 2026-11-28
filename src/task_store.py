"""État des tâches, rapports et problèmes (SQLite) : contrat §6.7."""
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Optional

from src.config import load_config
from src.models import Finding, SlackInfo, Task

# Statuts internes (§6.1)
IN_PROGRESS = "in_progress"
AWAITING_REVIEW = "awaiting_review"
PR_OPENED = "pr_opened"
COMPLETED = "completed"
FAILED = "failed"
STATUSES = {IN_PROGRESS, AWAITING_REVIEW, PR_OPENED, COMPLETED, FAILED}

BRANCH_MODES = {"task", "fix", "docs"}      # seuls modes qui créent une branche
UPDATABLE = {"jira_key", "branch", "revision", "feedback", "summary", "pr_url", "description"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    description TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    jira_key TEXT,
    branch TEXT,
    revision INTEGER NOT NULL DEFAULT 0,
    feedback TEXT,
    slack_channel_id TEXT NOT NULL,
    slack_thread_ts TEXT NOT NULL,
    slack_user_id TEXT NOT NULL,
    summary TEXT,
    pr_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    json TEXT NOT NULL,
    PRIMARY KEY (report_id, finding_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(load_config().db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)          # idempotent : crée les tables au premier appel
    return conn


def _slug(text: str, max_len: int = 30) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:max_len].strip("-")
    return slug or "task"


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        task_id=row["task_id"], mode=row["mode"], description=row["description"],
        params=json.loads(row["params"]), jira_key=row["jira_key"],
        slack=SlackInfo(channel_id=row["slack_channel_id"],
                        thread_ts=row["slack_thread_ts"], user_id=row["slack_user_id"]),
        branch=row["branch"], repo_path=load_config().workspace_dir,
        revision=row["revision"], feedback=row["feedback"],
    )


def create_task(mode: str, description: str, params: dict[str, Any], slack: SlackInfo) -> Task:
    """Crée la tâche : task_id auto (T-0001...), branche agent/<id>-<slug> si mode d'écriture."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")             # évite deux ids identiques en parallèle
        last = conn.execute(
            "SELECT MAX(CAST(SUBSTR(task_id, 3) AS INTEGER)) FROM tasks").fetchone()[0] or 0
        task_id = f"T-{last + 1:04d}"
        branch = f"agent/{task_id}-{_slug(description)}" if mode in BRANCH_MODES else None
        now = _now()
        conn.execute(
            "INSERT INTO tasks (task_id, mode, description, params, status, branch, revision,"
            " slack_channel_id, slack_thread_ts, slack_user_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,0,?,?,?,?,?)",
            (task_id, mode, description, json.dumps(params or {}), IN_PROGRESS, branch,
             slack.channel_id, slack.thread_ts, slack.user_id, now, now))
        conn.commit()
    return get_task(task_id)


def update_status(task_id: str, status: str, **fields: Any) -> None:
    if status not in STATUSES:
        raise ValueError(f"Statut inconnu : {status}")
    bad = set(fields) - UPDATABLE
    if bad:
        raise ValueError(f"Champs non modifiables : {sorted(bad)}")
    cols = ["status = ?", "updated_at = ?"] + [f"{k} = ?" for k in fields]
    values = [status, _now(), *fields.values(), task_id]
    with closing(_connect()) as conn:
        cur = conn.execute(f"UPDATE tasks SET {', '.join(cols)} WHERE task_id = ?", values)
        if cur.rowcount == 0:
            raise KeyError(f"Tâche introuvable : {task_id}")
        conn.commit()


def get_task(task_id: str) -> Task:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(f"Tâche introuvable : {task_id}")
    return _row_to_task(row)


def get_status(task_id: str) -> str:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(f"Tâche introuvable : {task_id}")
    return row["status"]


def list_tasks() -> list[Task]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY task_id DESC").fetchall()
    return [_row_to_task(r) for r in rows]


def save_report(report) -> None:
    """report : objet Pydantic avec report_id, task_id, findings (§6.9)."""
    data = report.model_dump()
    now = _now()
    with closing(_connect()) as conn:
        conn.execute("INSERT OR REPLACE INTO reports (report_id, task_id, json, created_at)"
                     " VALUES (?,?,?,?)",
                     (data["report_id"], data["task_id"], json.dumps(data), now))
        for f in data["findings"]:
            conn.execute("INSERT OR REPLACE INTO findings (finding_id, report_id, json)"
                         " VALUES (?,?,?)", (f["finding_id"], data["report_id"], json.dumps(f)))
        conn.commit()


def get_finding(finding_id: str) -> Finding:
    """Cherche dans le rapport le plus récent (les F-xxxx repartent de F-0001 à chaque audit)."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT f.json FROM findings f JOIN reports r ON r.report_id = f.report_id"
            " WHERE f.finding_id = ? ORDER BY r.created_at DESC, r.report_id DESC LIMIT 1",
            (finding_id,)).fetchone()
    if row is None:
        raise KeyError(f"Problème introuvable : {finding_id}")
    return Finding(**json.loads(row["json"]))