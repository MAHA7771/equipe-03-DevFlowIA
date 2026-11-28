"""Opérations Git (P3) : branche, diff, commit, push.

Règles de sécurité (§1.5) :
- aucun commit ni push avant l'approbation (commit_and_push n'est appelé
  par le pipeline qu'après le clic sur « Approuver ») ;
- jamais de push sur main : uniquement sur agent/... ;
- le token GitHub n'est jamais écrit dans .git/config (en-tête HTTP temporaire).
"""
import base64
import os
import subprocess
from pathlib import Path

from src.models import DiffReport, FileDiff

MAX_DIFF_CHARS = 3000
PROTECTED_BRANCHES = {"main", "master"}


def _mask(text: str) -> str:
    """Masque le token GitHub dans les messages d'erreur."""
    token = os.getenv("GITHUB_TOKEN", "")
    return text.replace(token, "****") if token else text


def _auth_args() -> list[str]:
    """En-tête d'authentification GitHub (HTTPS) sans stocker le token."""
    token = os.getenv("GITHUB_TOKEN", "")
    if not token or os.getenv("GIT_REMOTE_URL"):
        return []
    raw = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.extraheader=AUTHORIZATION: basic {raw}"]


def _remote_url() -> str:
    return os.getenv("GIT_REMOTE_URL") or f"https://github.com/{os.environ['GITHUB_REPO']}.git"


def run_git(repo_path: str, *args: str, check: bool = True, auth: bool = False) -> str:
    """Lance une commande git dans repo_path et renvoie stdout (strippé)."""
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    name = os.getenv("AGENT_GIT_NAME", "dev-agent")
    email = os.getenv("AGENT_GIT_EMAIL", "dev-agent@users.noreply.github.com")
    env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
               GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
    cmd = ["git", *(_auth_args() if auth else []), *args]
    r = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if check and r.returncode != 0:
        raise RuntimeError(_mask(f"git {' '.join(args)} a échoué : {r.stderr.strip() or r.stdout.strip()}"))
    return r.stdout.strip()


def _branch_exists(repo_path: str, branch: str) -> bool:
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                       cwd=repo_path, capture_output=True)
    return r.returncode == 0


def prepare_branch(repo_path: str, branch: str, base: str) -> None:
    """Clone ou met à jour le repo, puis crée la branche (ou la réutilise)."""
    repo = Path(repo_path)
    if not (repo / ".git").exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", *_auth_args(), "clone", _remote_url(), str(repo)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode != 0:
            raise RuntimeError(_mask(f"git clone a échoué : {r.stderr.strip()}"))
    else:
        run_git(repo_path, "fetch", "origin", auth=True)

    if _branch_exists(repo_path, branch):
        run_git(repo_path, "checkout", branch)      # branche réutilisée (rejet, relance)
        return

    # Nouvelle branche : on repart d'un état propre de la branche de base.
    run_git(repo_path, "reset", "--hard", "HEAD", check=False)
    run_git(repo_path, "clean", "-fd")
    run_git(repo_path, "checkout", base)
    run_git(repo_path, "pull", "--ff-only", "origin", base, auth=True)
    run_git(repo_path, "checkout", "-b", branch)


def get_diff(repo_path: str, task_id: str) -> DiffReport:
    """Diff de l'espace de travail contre HEAD, fichiers non suivis inclus."""
    run_git(repo_path, "add", "-A")                 # inclut les fichiers nouveaux
    files: list[FileDiff] = []
    for line in run_git(repo_path, "diff", "--cached", "--numstat").splitlines():
        add, dele, path = line.split("\t", 2)
        files.append(FileDiff(path=path,
                              additions=int(add) if add.isdigit() else 0,   # binaire : "-"
                              deletions=int(dele) if dele.isdigit() else 0))
    text = run_git(repo_path, "diff", "--cached")
    if len(text) > MAX_DIFF_CHARS:
        text = text[:MAX_DIFF_CHARS] + "\n... (diff tronqué)"
    return DiffReport(task_id=task_id, files=files, diff_text=text)


def commit_and_push(repo_path: str, branch: str, message: str) -> str:
    """Commit + push de la branche de l'agent. Renvoie le SHA court du commit."""
    if branch in PROTECTED_BRANCHES or not branch.startswith("agent/"):
        raise ValueError(f"Push refusé sur '{branch}' : seules les branches agent/... sont autorisées")
    current = run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    if current != branch:
        raise RuntimeError(f"La branche courante est '{current}', attendu '{branch}'")
    run_git(repo_path, "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_path).returncode == 0:
        raise RuntimeError("Rien à committer : aucun fichier modifié")
    run_git(repo_path, "commit", "-m", message)
    sha = run_git(repo_path, "rev-parse", "--short", "HEAD")
    run_git(repo_path, "push", "-u", "origin", branch, auth=True)
    return sha
