"""Faux temporaires de P2 (§8) : utilisés par pipeline.py tant que les vrais modules sont vides."""
from pathlib import Path

from src.models import AgentResult, AgentTests, Finding, RepoAnswer, RepoFile, Task


def run_agent(task: Task, on_checkpoint) -> AgentResult:
    """Ajoute une ligne dans un fichier, déclenche un checkpoint, renvoie un résultat fixe."""
    path = Path(task.repo_path) / "AGENT_STUB.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"stub {task.task_id} r{task.revision} feedback={task.feedback}\n")
    on_checkpoint("iter-1")
    return AgentResult(
        task_id=task.task_id, status="success",
        summary=f"[FAUX] Ligne ajoutée dans AGENT_STUB.md (révision {task.revision}).",
        explanation="[FAUX] Explication fictive." if task.mode == "fix" else None,
        files_changed=["AGENT_STUB.md"],
        tests=AgentTests(ran=True, passed=True, output="1 passed"), iterations=1)


def run_security_audit(repo_path: str) -> list[Finding]:
    """Trois problèmes fixes : un secret, une SQL injection, un XSS (triés par gravité)."""
    return [
        Finding(finding_id="F-0001", rule="exposed_secret", backlog_task="TASK-42",
                severity="critical", file="backend/.env.local", line=3,
                title="Secret exposé dans le code", evidence="sk-l****",
                recommendation="Déplacer le secret dans .env", confidence=0.9, source="regex"),
        Finding(finding_id="F-0002", rule="sql_injection", backlog_task="TASK-40",
                severity="high", file="backend/app/products.py", line=42,
                title="Requête SQL construite par concaténation",
                evidence='cursor.execute("SELECT ... " + name)',
                recommendation="Utiliser une requête paramétrée", confidence=0.8, source="regex"),
        Finding(finding_id="F-0003", rule="xss", backlog_task="TASK-41",
                severity="high", file="frontend/src/pages/Products.jsx", line=17,
                title="HTML injecté sans échappement", evidence="dangerouslySetInnerHTML",
                recommendation="Échapper la valeur affichée", confidence=0.8, source="regex"),
    ]


def answer_question(repo_path: str, question: str) -> RepoAnswer:
    return RepoAnswer(question=question, answer="[FAUX] Réponse fictive.",
                      files=[RepoFile(path="backend/app/auth.py", reason="exemple")])