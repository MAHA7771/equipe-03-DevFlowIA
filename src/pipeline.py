"""Pipeline (P1) : machine à états d'une demande, Slack -> Jira -> agent -> validation -> PR.

Appelle P2 (run_agent, run_security_audit, answer_question) et P3 (git, checkpoints, PR, revue).
Le clone de travail est unique : un verrou met les tâches en file d'attente, et l'état de chaque
tâche est reconstruit depuis ses checkpoints avant chaque décision.
"""
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from src import checkpoints, git_ops, github_client, jira_client, review, task_store
from src.config import load_config
from src.models import (AgentResult, DiffReport, Finding, ReviewDecision, Score,
                        SecurityReport, Task)
from src.security.score import compute_score, count_by_severity

# --- P2 : vrais modules si disponibles, sinon faux temporaires -----------------------------
STUBS_IN_USE: list[str] = []
try:
    from src.agent.agent_loop import run_agent
except ImportError:
    from src.dev_stubs import run_agent
    STUBS_IN_USE.append("run_agent")
try:
    from src.security.runner import run_security_audit
except ImportError:
    from src.dev_stubs import run_security_audit
    STUBS_IN_USE.append("run_security_audit")
try:
    from src.agent.repo_qa import answer_question
except ImportError:
    from src.dev_stubs import answer_question
    STUBS_IN_USE.append("answer_question")
try:
    from src.quality.analyze import analyze_code
except ImportError:
    analyze_code = None
    STUBS_IN_USE.append("analyze_code")
if STUBS_IN_USE:
    print(f"[pipeline] faux temporaires utilisés : {', '.join(STUBS_IN_USE)}")

WRITE_MODES = {"task", "fix", "docs"}
_WORKSPACE = threading.RLock()          # un seul clone de travail : une tâche à la fois
_DECISION_LOCK = threading.Lock()
_deciding: set[str] = set()             # anti double-clic sur Approuver / Rejeter
_SECRET_VARS = ("GITHUB_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "JIRA_API_TOKEN", "GROQ_API_KEY")


class AgentFailed(RuntimeError):
    pass


# --- utilitaires ---------------------------------------------------------------------------
def _mask(text: str) -> str:
    for var in _SECRET_VARS:
        value = os.getenv(var, "")
        if len(value) >= 8:
            text = text.replace(value, "****")
    return text


def _background(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


def _say(task: Task, text: str) -> None:
    """Message dans le fil Slack (slack_app.post_message, écrit à l'étape suivante)."""
    try:
        from src import slack_app
        slack_app.post_message(task, text)
    except (ImportError, AttributeError):
        print(f"[slack:factice] {task.task_id} : {text[:200]}")


def _say_audit(task: Task, report: SecurityReport) -> None:
    try:
        from src import slack_app
        slack_app.post_audit_report(task, report)
    except (ImportError, AttributeError):
        print(f"[slack:factice] {task.task_id} : audit score {report.score.value}/100")


def _open_issue(task: Task) -> Task:
    key = jira_client.create_issue(task)
    task_store.update_status(task.task_id, task_store.IN_PROGRESS, jira_key=key)
    return task.model_copy(update={"jira_key": key})


def _clean_workspace(repo_path: str) -> None:
    if (Path(repo_path) / ".git").exists():
        git_ops.run_git(repo_path, "reset", "--hard", "HEAD", check=False)
        git_ops.run_git(repo_path, "clean", "-fd")


def _enter_base(repo_path: str) -> None:
    """Modes en lecture seule : clone propre sur la branche de base, à jour."""
    base = load_config().base_branch
    _clean_workspace(repo_path)
    git_ops.prepare_branch(repo_path, base, base)
    git_ops.run_git(repo_path, "pull", "--ff-only", "origin", base, check=False, auth=True)


def _checkout_task_branch(task: Task) -> None:
    _clean_workspace(task.repo_path)
    git_ops.prepare_branch(task.repo_path, task.branch, load_config().base_branch)


def _resume(task: Task) -> None:
    """Reconstruit l'état de la tâche : sa branche + son dernier checkpoint agent_done."""
    _checkout_task_branch(task)
    for cp in checkpoints.list_checkpoints(task.repo_path, task.task_id):   # du plus récent
        if cp.label.startswith("agent_done"):
            checkpoints.restore_checkpoint(task.repo_path, cp.checkpoint_id)
            return


# --- textes Jira / Slack -------------------------------------------------------------------
def format_report(report: SecurityReport) -> str:
    """Rapport d'audit en texte. Le champ evidence est volontairement omis (jamais de secret)."""
    c = report.counts
    lines = [
        f"Security Score : {report.score.value}/100 (note {report.score.grade})",
        f"Critical : {c.get('critical', 0)} | High : {c.get('high', 0)} | "
        f"Medium : {c.get('medium', 0)} | Low : {c.get('low', 0)}",
        "",
    ]
    for f in report.findings:
        lines.append(f"- {f.finding_id} [{f.severity}] {f.rule} : {f.file}:{f.line} : {f.title}")
    return "\n".join(lines)


def _format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "Aucun problème détecté."
    return "\n".join(f"- [{f.rule}] {f.file}:{f.line} : {f.title}" for f in findings)


def _review_comment(result: AgentResult, diff: DiffReport) -> str:
    files = "\n".join(f"* {f.path} (+{f.additions} / -{f.deletions})" for f in diff.files) or "(aucun)"
    tests = "non lancés" if not result.tests.ran else ("passés" if result.tests.passed else "échoués")
    return (f"Résumé : {result.summary}\n\nFichiers modifiés :\n{files}\n\nTests : {tests}\n\n"
            f"{{code}}\n{diff.diff_text}\n{{code}}")


def build_report(task: Task, findings: list[Finding]) -> SecurityReport:
    return SecurityReport(
        report_id=f"R-{task.task_id[2:]}", task_id=task.task_id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        findings=findings, counts=count_by_severity(findings),
        score=Score(**compute_score(findings)))


# --- échec ---------------------------------------------------------------------------------
def _fail(task: Task, exc: Exception) -> None:
    """Toute exception : dernier checkpoint sain restauré, statut failed, erreur dans Jira."""
    msg = _mask(f"{type(exc).__name__} : {exc}")
    print(f"[pipeline] {task.task_id} a échoué : {msg}")
    try:
        cps = checkpoints.list_checkpoints(task.repo_path, task.task_id)
        if cps:
            checkpoints.restore_checkpoint(task.repo_path, cps[0].checkpoint_id)
    except Exception as restore_exc:
        print(f"[pipeline] restauration impossible : {_mask(str(restore_exc))}")
    try:
        task_store.update_status(task.task_id, task_store.FAILED)
        if task.jira_key:
            jira_client.add_comment(task.jira_key, f"Échec de l'agent : {msg}")
            jira_client.add_label(task.jira_key, "agentfailed")
    except Exception as jira_exc:
        print(f"[pipeline] Jira indisponible pendant l'échec : {_mask(str(jira_exc))}")
    _say(task, f":x: {task.task_id} a échoué : {msg}\nLe dernier checkpoint sain a été restauré.")


# --- étapes communes aux modes qui modifient le code ---------------------------------------
def _work_and_review(task: Task) -> None:
    repo = task.repo_path
    result = run_agent(task, on_checkpoint=lambda label: checkpoints.create_checkpoint(
        repo, task.task_id, label))
    if result.status == "failed":
        raise AgentFailed(result.error or "échec de l'agent")
    checkpoints.create_checkpoint(repo, task.task_id, f"agent_done_r{task.revision}")
    diff = git_ops.get_diff(repo, task.task_id)
    jira_client.add_comment(task.jira_key, _review_comment(result, diff))
    jira_client.transition(task.jira_key, "done")
    task_store.update_status(task.task_id, task_store.AWAITING_REVIEW, summary=result.summary)
    review.post_review_request(task, result, diff)


# --- point d'entrée ------------------------------------------------------------------------
def start_task(task: Task) -> None:
    try:
        if task.mode == "fix":
            task_store.get_finding(task.params["finding_id"])       # échoue tôt si inconnu
        task = _open_issue(task)
        with _WORKSPACE:
            if task.mode in WRITE_MODES:
                git_ops.prepare_branch(task.repo_path, task.branch, load_config().base_branch)
                checkpoints.create_checkpoint(task.repo_path, task.task_id, "start")
                _work_and_review(task)
            elif task.mode == "audit":
                _enter_base(task.repo_path)
                findings = run_security_audit(task.repo_path)
                report = build_report(task, findings)
                task_store.save_report(report)
                _say_audit(task, report)
                jira_client.add_comment(task.jira_key, format_report(report))
                jira_client.transition(task.jira_key, "done")
                task_store.update_status(task.task_id, task_store.COMPLETED,
                                         summary=f"Score {report.score.value}/100 ({report.score.grade})")
            elif task.mode in ("ask", "analyze"):
                _enter_base(task.repo_path)
                if task.mode == "ask":
                    answer = answer_question(task.repo_path, task.params["question"])
                    files = "\n".join(f"- {f.path} : {f.reason}" for f in answer.files)
                    text = f"{answer.answer}\n\nFichiers concernés :\n{files}"
                else:
                    if analyze_code is None:
                        raise RuntimeError("analyze_code n'est pas disponible")
                    text = _format_findings(analyze_code(task.repo_path))
                _say(task, text)
                jira_client.add_comment(task.jira_key, text)
                jira_client.transition(task.jira_key, "done")
                task_store.update_status(task.task_id, task_store.COMPLETED, summary=text[:200])
            else:
                raise ValueError(f"Mode inconnu : {task.mode}")
    except Exception as exc:
        _fail(task, exc)


# --- décision du développeur (appelée par les boutons de P3) -------------------------------
def on_review_decision(decision: ReviewDecision) -> None:
    try:
        task = task_store.get_task(decision.task_id)
    except KeyError:
        print(f"[pipeline] décision pour une tâche inconnue : {decision.task_id}")
        return
    with _DECISION_LOCK:
        if task.task_id in _deciding or task_store.get_status(task.task_id) != task_store.AWAITING_REVIEW:
            _say(task, f"{task.task_id} n'attend plus de validation (décision déjà prise).")
            return
        _deciding.add(task.task_id)
    _background(_process_decision, task, decision)


def _process_decision(task: Task, decision: ReviewDecision) -> None:
    try:
        with _WORKSPACE:
            if decision.decision == "approved":
                _approve(task)
            else:
                _reject(task, decision.feedback or "")
    except Exception as exc:
        _fail(task, exc)
    finally:
        _deciding.discard(task.task_id)


def _approve(task: Task) -> None:
    _resume(task)
    title = f"[{task.task_id}] {task.description}"[:72]
    git_ops.commit_and_push(task.repo_path, task.branch, title)
    body = (f"Demande : {task.description}\nIssue Jira : {task.jira_key}\n\n"
            "Générée par dev-agent, à relire avant de fusionner.")
    pr = github_client.open_pull_request(task.branch, title, body)
    task_store.update_status(task.task_id, task_store.PR_OPENED, pr_url=pr.pr_url)
    jira_client.add_comment(task.jira_key, f"Pull Request ouverte : {pr.pr_url}")
    _say(task, f":tada: PR #{pr.pr_number} ouverte : {pr.pr_url}")


def _reject(task: Task, feedback: str) -> None:
    revision = task.revision + 1
    task_store.update_status(task.task_id, task_store.IN_PROGRESS, revision=revision, feedback=feedback)
    jira_client.transition(task.jira_key, "in_progress")
    jira_client.add_comment(task.jira_key, f"Rejeté (révision {revision}) : {feedback}")
    task = task_store.get_task(task.task_id)
    _say(task, f":arrows_counterclockwise: L'agent retravaille {task.task_id} avec ton commentaire.")
    _resume(task)
    _work_and_review(task)


# --- /agent restore ------------------------------------------------------------------------
def restore(task_id: str, checkpoint_id: str) -> str:
    """Restauration manuelle. checkpoint_id : 'T-0001/003', ou seulement 'start' / '003'."""
    task = task_store.get_task(task_id)
    if not task.branch:
        return f"{task_id} est une demande en lecture seule : aucun checkpoint à restaurer."
    if "/" not in checkpoint_id:
        checkpoint_id = f"{task_id}/{checkpoint_id}"
    with _WORKSPACE:
        _checkout_task_branch(task)
        checkpoints.restore_checkpoint(task.repo_path, checkpoint_id)
    return f"Espace de travail de {task_id} restauré au checkpoint {checkpoint_id}."