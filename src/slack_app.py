"""Entrée Slack (P1) : commande /agent, bouton « Corriger », messages et rapport d'audit."""
import re
import threading
from dataclasses import dataclass
from typing import Optional

from src import pipeline, task_store
from src.models import SecurityReport, SlackInfo, Task

_client = None                      # WebClient, fixé par register()
_CREATE_LOCK = threading.Lock()

FINDING_RE = re.compile(r"F-\d{4}")
TASK_RE = re.compile(r"T-\d{4}")
DOCS_KINDS = {"readme", "api", "architecture", "install"}
MAX_BUTTONS = 5
ACTIVE = {task_store.IN_PROGRESS, task_store.AWAITING_REVIEW}

USAGE = (
    "*Commandes /agent*\n"
    "• `/agent audit` : audit de sécurité avec Security Score\n"
    "• `/agent fix F-0007` : corriger un problème détecté\n"
    "• `/agent ask <question>` : question sur le code\n"
    "• `/agent docs readme|api|architecture|install` : générer de la documentation\n"
    "• `/agent analyze` : analyse de la qualité du code\n"
    "• `/agent restore T-0001 start` : restaurer un checkpoint\n"
    "• `/agent <description>` : tâche de développement libre"
)

GRADE_EMOJI = {"A": ":large_green_circle:", "B": ":large_green_circle:",
               "C": ":large_yellow_circle:", "D": ":large_orange_circle:", "E": ":red_circle:"}
SEV_EMOJI = {"critical": ":rotating_light:", "high": ":red_circle:",
             "medium": ":large_orange_circle:", "low": ":large_blue_circle:"}


class UsageError(ValueError):
    """Commande mal formée : le message est montré tel quel à l'utilisateur."""


@dataclass
class Command:
    mode: str                                   # task, fix, docs, audit, ask, analyze, restore
    description: str
    params: dict
    restore: Optional[tuple[str, str]] = None   # (task_id, checkpoint) pour /agent restore


# --- parsing -------------------------------------------------------------------------------
def parse_command(text: str) -> Command:
    text = (text or "").strip()
    if not text or text.lower() in ("help", "aide"):
        raise UsageError(USAGE)
    word, _, rest = text.partition(" ")
    key, rest = word.lower(), rest.strip()

    if key in ("audit", "analyze"):
        return Command(key, f"{key} du dépôt", {})
    if key == "fix" and FINDING_RE.fullmatch(rest.upper()):
        fid = rest.upper()
        return Command("fix", f"Corriger {fid}", {"finding_id": fid})
    if key == "ask":
        if not rest:
            raise UsageError("Pose ta question : `/agent ask <question>`")
        return Command("ask", rest, {"question": rest})
    if key == "docs":
        if rest.lower() not in DOCS_KINDS:
            raise UsageError("Type de documentation : `readme`, `api`, `architecture` ou `install`.")
        return Command("docs", f"Générer la documentation ({rest.lower()})", {"kind": rest.lower()})
    if key == "restore":
        parts = rest.split()
        if len(parts) != 2 or not TASK_RE.fullmatch(parts[0].upper()):
            raise UsageError("Usage : `/agent restore T-0001 start` (ou un numéro de checkpoint)")
        return Command("restore", "restore", {}, restore=(parts[0].upper(), parts[1]))
    return Command("task", text, {})            # tout le reste : tâche de développement libre


# --- messages ------------------------------------------------------------------------------
def post_message(task: Task, text: str) -> None:
    """Message dans le fil de la tâche (appelé par pipeline._say)."""
    if _client is None:
        print(f"[slack:factice] {task.task_id} : {text[:200]}")
        return
    _client.chat_postMessage(channel=task.slack.channel_id, thread_ts=task.slack.thread_ts,
                             text=text[:3900])


def build_audit_blocks(task, report: SecurityReport) -> list[dict]:
    c = report.counts
    emoji = GRADE_EMOJI.get(report.score.grade, "")
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Audit de sécurité : {task.task_id}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"{emoji} *Security Score : {report.score.value}/100* (note *{report.score.grade}*)\n"
            f"Critical : {c.get('critical', 0)} · High : {c.get('high', 0)} · "
            f"Medium : {c.get('medium', 0)} · Low : {c.get('low', 0)}")}},
    ]
    top = report.findings[:MAX_BUTTONS]
    if not top:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "Aucun problème détecté :white_check_mark:"}})
    for f in top:                               # l'evidence n'est jamais affichée (secrets)
        where = f"`{f.file}:{f.line}`" if f.line else f"`{f.file}`"
        text = f"{SEV_EMOJI.get(f.severity, '')} *{f.finding_id}* · {f.rule} · {where}\n{f.title}"
        blocks.append({
            "type": "section", "block_id": f"finding_{f.finding_id}",
            "text": {"type": "mrkdwn", "text": text[:2900]},
            "accessory": {"type": "button", "action_id": "fix_finding", "value": f.finding_id,
                          "text": {"type": "plain_text", "text": "Corriger"}},
        })
    rest = len(report.findings) - len(top)
    if rest > 0:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": (
            f"… et {rest} autres problèmes : voir le commentaire Jira. "
            "Pour en corriger un : `/agent fix F-xxxx`")}]})
    return blocks


def post_audit_report(task: Task, report: SecurityReport) -> None:
    """Rapport d'audit avec score et boutons « Corriger » (appelé par pipeline._say_audit)."""
    blocks = build_audit_blocks(task, report)
    if _client is None:
        print(f"[slack:factice] audit {task.task_id} : {len(blocks)} blocs")
        return
    _client.chat_postMessage(
        channel=task.slack.channel_id, thread_ts=task.slack.thread_ts,
        text=f"Audit {task.task_id} : Security Score {report.score.value}/100", blocks=blocks)


def _ephemeral(client, channel_id: str, user_id: str, text: str) -> None:
    try:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)
    except Exception as exc:
        print(f"[slack_app] message éphémère impossible : {exc}")


# --- lancement d'une tâche -----------------------------------------------------------------
def _active_fix(finding_id: str) -> bool:
    return any(t.mode == "fix" and t.params.get("finding_id") == finding_id
               and task_store.get_status(t.task_id) in ACTIVE
               for t in task_store.list_tasks())


def launch(client, channel_id: str, user_id: str, command: Command, intro: str) -> Optional[Task]:
    """Message racine -> Task -> pipeline en tâche de fond. Renvoie None si doublon de fix."""
    if command.mode == "fix":
        fid = command.params["finding_id"]
        try:
            finding = task_store.get_finding(fid)
        except KeyError:
            raise UsageError(f"Problème `{fid}` introuvable : lance d'abord `/agent audit`.")
        command = Command("fix", f"Corriger {fid} : {finding.title}", command.params)
    with _CREATE_LOCK:                          # le contrôle de doublon et la création vont ensemble
        if command.mode == "fix" and _active_fix(command.params["finding_id"]):
            return None
        root = client.chat_postMessage(channel=channel_id, text=intro)
        task = task_store.create_task(command.mode, command.description, command.params,
                                      SlackInfo(channel_id=channel_id, thread_ts=root["ts"], user_id=user_id))
    client.chat_postMessage(channel=channel_id, thread_ts=root["ts"], text=(
        f":hourglass_flowing_sand: {task.task_id} prise en charge (mode `{task.mode}`)"
        + (f", branche `{task.branch}`" if task.branch else "")))
    pipeline._background(pipeline.start_task, task)
    return task


def _restore_and_report(task: Task, checkpoint: str) -> None:
    try:
        msg = pipeline.restore(task.task_id, checkpoint)
    except Exception as exc:
        msg = f"Restauration impossible : {pipeline._mask(str(exc))}"
    post_message(task, msg)


# --- branchement sur l'app Bolt ------------------------------------------------------------
def register(app) -> None:
    global _client
    _client = app.client

    @app.command("/agent")
    def on_command(ack, command, client):
        ack()                                   # obligatoire en moins de 3 s
        channel, user, text = command["channel_id"], command["user_id"], command.get("text", "")
        try:
            cmd = parse_command(text)
            if cmd.restore:
                task_id, checkpoint = cmd.restore
                task = task_store.get_task(task_id)
                _ephemeral(client, channel, user, f"Restauration de {task_id} demandée…")
                pipeline._background(_restore_and_report, task, checkpoint)
                return
            task = launch(client, channel, user, cmd, f"<@{user}> : `/agent {text.strip()}`")
            if task is None:
                _ephemeral(client, channel, user, "Une correction de ce problème est déjà en cours.")
        except UsageError as exc:
            _ephemeral(client, channel, user, str(exc))
        except KeyError:
            _ephemeral(client, channel, user, "Tâche introuvable.")
        except Exception as exc:
            print(f"[slack_app] erreur : {pipeline._mask(str(exc))}")
            _ephemeral(client, channel, user, "Erreur interne : voir les logs du bot.")

    @app.action("fix_finding")
    def on_fix(ack, body, client):
        ack()
        finding_id = body["actions"][0]["value"]
        user, channel = body["user"]["id"], body["container"]["channel_id"]
        try:
            cmd = Command("fix", f"Corriger {finding_id}", {"finding_id": finding_id})
            task = launch(client, channel, user, cmd, f"<@{user}> : correction de `{finding_id}`")
            if task is None:
                _ephemeral(client, channel, user, f"Une correction de `{finding_id}` est déjà en cours.")
        except UsageError as exc:
            _ephemeral(client, channel, user, str(exc))
        except Exception as exc:
            print(f"[slack_app] erreur : {pipeline._mask(str(exc))}")
            _ephemeral(client, channel, user, "Erreur interne : voir les logs du bot.")