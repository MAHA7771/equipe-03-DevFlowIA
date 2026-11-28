"""Validation dans Slack (P3) : message de revue, boutons, modale de rejet.

Contrat Slack (§7) :
- bouton Approuver : action_id="approve_task", value=task_id
- bouton Rejeter   : action_id="reject_task",  value=task_id -> ouvre une modale
  (callback_id="reject_feedback_modal", block_id="feedback", action_id="feedback_input")

P1 branche ce module dans main.py :
    from src import review
    review.register_handlers(app)
"""
from typing import Optional

from src.models import AgentResult, DiffReport, ReviewDecision, Task

_client = None          # slack_sdk WebClient, fixé par register_handlers()

DIFF_MAX = 2400         # un bloc Slack accepte 3000 caractères au maximum


def build_review_blocks(task: Task, result: AgentResult, diff: DiffReport) -> list[dict]:
    t = result.tests
    if not t.ran:
        tests_txt = "⚪ non lancés"
    else:
        tests_txt = "✅ passés" if t.passed else "❌ échoués"
    files = "\n".join(f"• `{f.path}` (+{f.additions} / -{f.deletions})" for f in diff.files) \
        or "_aucun fichier modifié_"

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Revue : {task.task_id}"[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Résumé*\n{result.summary or '_aucun résumé_'}"[:2900]}},
    ]
    if result.explanation:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": f"*Explication*\n{result.explanation}"[:2900]}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
                   "text": f"*Fichiers modifiés*\n{files}\n*Tests* : {tests_txt}"[:2900]}})
    if t.ran and not t.passed and t.output:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": f"```{t.output[-800:]}```"}})
    if diff.diff_text:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": f"*Diff*\n```{diff.diff_text[:DIFF_MAX]}```"}})
    blocks.append({"type": "actions", "block_id": f"review_{task.task_id}", "elements": [
        {"type": "button", "action_id": "approve_task", "value": task.task_id, "style": "primary",
         "text": {"type": "plain_text", "text": "Approuver"}},
        {"type": "button", "action_id": "reject_task", "value": task.task_id, "style": "danger",
         "text": {"type": "plain_text", "text": "Rejeter"}},
    ]})
    return blocks


def post_review_request(task: Task, result: AgentResult, diff: DiffReport) -> None:
    """Poste dans le thread : explication, diff, tests et boutons."""
    blocks = build_review_blocks(task, result, diff)
    if _client is None:                       # pas de Slack (tests, mode factice)
        print(f"[review] {task.task_id} : {len(blocks)} blocs, pas de client Slack")
        return
    _client.chat_postMessage(
        channel=task.slack.channel_id, thread_ts=task.slack.thread_ts,
        text=f"Revue demandée pour {task.task_id}", blocks=blocks)


def _freeze_buttons(client, body: dict, text: str) -> None:
    """Remplace les boutons par un texte : évite un double clic (double PR)."""
    try:
        msg = body["message"]
        blocks = [b for b in msg.get("blocks", []) if b.get("type") != "actions"]
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": text}]})
        client.chat_update(channel=body["container"]["channel_id"], ts=msg["ts"],
                           text=msg.get("text", "Revue"), blocks=blocks)
    except Exception as exc:                  # cosmétique : ne doit jamais bloquer la décision
        print(f"[review] chat_update ignoré : {exc}")


def reject_modal(task_id: str) -> dict:
    return {
        "type": "modal", "callback_id": "reject_feedback_modal",
        "private_metadata": task_id,
        "title": {"type": "plain_text", "text": "Rejeter la proposition"},
        "submit": {"type": "plain_text", "text": "Envoyer"},
        "close": {"type": "plain_text", "text": "Annuler"},
        "blocks": [{
            "type": "input", "block_id": "feedback",
            "label": {"type": "plain_text", "text": "Que faut-il changer ?"},
            "element": {"type": "plain_text_input", "action_id": "feedback_input", "multiline": True},
        }],
    }


def register_handlers(app) -> None:
    """Enregistre les boutons et la modale sur l'app Slack Bolt (P1 l'appelle)."""
    global _client
    _client = app.client

    from src import pipeline          # import tardif : évite une boucle d'import

    @app.action("approve_task")
    def on_approve(ack, body, client):
        ack()
        task_id = body["actions"][0]["value"]
        user = body["user"]["id"]
        _freeze_buttons(client, body, f"✅ Approuvé par <@{user}>")
        pipeline.on_review_decision(ReviewDecision(
            task_id=task_id, decision="approved", feedback=None, reviewer_slack_id=user))

    @app.action("reject_task")
    def on_reject(ack, body, client):
        ack()
        task_id = body["actions"][0]["value"]
        client.views_open(trigger_id=body["trigger_id"], view=reject_modal(task_id))

    @app.view("reject_feedback_modal")
    def on_feedback(ack, body, view):
        feedback: Optional[str] = view["state"]["values"]["feedback"]["feedback_input"]["value"]
        if not feedback or not feedback.strip():
            ack(response_action="errors",
                errors={"feedback": "Écris ce qu'il faut changer pour que l'agent puisse retravailler."})
            return
        ack()
        pipeline.on_review_decision(ReviewDecision(
            task_id=view["private_metadata"], decision="rejected",
            feedback=feedback.strip(), reviewer_slack_id=body["user"]["id"]))
