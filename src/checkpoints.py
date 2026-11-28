"""Checkpoints (P3) : points de restauration de l'espace de travail.

Un checkpoint est un commit orphelin de la branche, référencé par
refs/agent/checkpoints/<task_id>/<n>. La branche ne bouge jamais et les
références ne sont jamais poussées.
"""
from datetime import datetime, timezone

from src.git_ops import run_git
from src.models import Checkpoint

PREFIX = "refs/agent/checkpoints"
KEEP = 10                       # on garde les 10 derniers par tâche
ALWAYS_KEEP = {"start"}         # le checkpoint de départ n'est jamais supprimé


def _files_changed(repo_path: str, commit: str) -> int:
    out = run_git(repo_path, "diff", "--name-only", "HEAD", commit, check=False)
    return len(out.splitlines()) if out else 0


def _number(ref: str) -> int:
    return int(ref.rsplit("/", 1)[1])


def create_checkpoint(repo_path: str, task_id: str, label: str) -> Checkpoint:
    existing = list_checkpoints(repo_path, task_id)
    n = (max(_number(c.ref) for c in existing) + 1) if existing else 1

    run_git(repo_path, "add", "-A")
    tree = run_git(repo_path, "write-tree")
    commit = run_git(repo_path, "commit-tree", tree, "-p", "HEAD", "-m", label)
    ref = f"{PREFIX}/{task_id}/{n:03d}"
    run_git(repo_path, "update-ref", ref, commit)

    cp = Checkpoint(
        checkpoint_id=f"{task_id}/{n:03d}", task_id=task_id, label=label, ref=ref,
        commit=commit[:7], files_changed=_files_changed(repo_path, commit),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    _prune(repo_path, task_id)
    return cp


def list_checkpoints(repo_path: str, task_id: str) -> list[Checkpoint]:
    """Du plus récent au plus ancien."""
    out = run_git(
        repo_path, "for-each-ref", "--sort=-refname",
        "--format=%(refname)\t%(objectname)\t%(contents:subject)\t%(creatordate:iso-strict)",
        f"{PREFIX}/{task_id}/",
    )
    result = []
    for line in out.splitlines():
        ref, sha, label, date = line.split("\t", 3)
        result.append(Checkpoint(
            checkpoint_id=ref.removeprefix(PREFIX + "/"), task_id=task_id, label=label,
            ref=ref, commit=sha[:7], files_changed=_files_changed(repo_path, sha),
            created_at=date,
        ))
    return result


def _prune(repo_path: str, task_id: str) -> None:
    for old in list_checkpoints(repo_path, task_id)[KEEP:]:
        if old.label not in ALWAYS_KEEP:
            run_git(repo_path, "update-ref", "-d", old.ref)


def _resolve(repo_path: str, checkpoint_id: str) -> str:
    """Accepte 'T-0001/003' (numéro) ou 'T-0001/start' (étiquette)."""
    if "/" not in checkpoint_id:
        raise ValueError("checkpoint_id attendu sous la forme <task_id>/<numéro ou étiquette>")
    task_id, key = checkpoint_id.split("/", 1)
    if key.isdigit():
        return f"{PREFIX}/{task_id}/{int(key):03d}"
    for cp in list_checkpoints(repo_path, task_id):          # le plus récent d'abord
        if cp.label == key:
            return cp.ref
    raise ValueError(f"Aucun checkpoint '{key}' pour la tâche {task_id}")


def restore_checkpoint(repo_path: str, checkpoint_id: str) -> None:
    """Remet l'espace de travail dans l'état du checkpoint (sans toucher aux commits)."""
    ref = _resolve(repo_path, checkpoint_id)
    run_git(repo_path, "rev-parse", "--verify", ref)          # erreur claire si inconnu
    run_git(repo_path, "reset", "--hard", "HEAD")
    run_git(repo_path, "clean", "-fd")
    run_git(repo_path, "checkout", ref, "--", ".")
    # Fichiers présents dans HEAD mais absents du checkpoint : à supprimer aussi.
    deleted = run_git(repo_path, "diff", "--name-only", "--diff-filter=D", "HEAD", ref)
    for path in deleted.splitlines():
        run_git(repo_path, "rm", "-q", "-f", "--", path)
