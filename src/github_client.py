"""Création de la Pull Request (P3). Jamais de merge automatique."""
import os
import re

from src.models import PRResult


def _task_id_from_branch(branch: str) -> str:
    m = re.match(r"agent/(T-\d+)", branch)
    return m.group(1) if m else ""


def open_pull_request(branch: str, title: str, body: str) -> PRResult:
    from github import Github          # import tardif : pas besoin de PyGithub pour les tests

    repo_name = os.environ["GITHUB_REPO"]
    base = os.getenv("BASE_BRANCH", "main")
    repo = Github(os.environ["GITHUB_TOKEN"]).get_repo(repo_name)

    # Si une PR est déjà ouverte pour cette branche, on la réutilise.
    owner = repo_name.split("/")[0]
    existing = list(repo.get_pulls(state="open", head=f"{owner}:{branch}", base=base))
    pr = existing[0] if existing else repo.create_pull(
        title=title, body=body, head=branch, base=base)

    return PRResult(
        task_id=_task_id_from_branch(branch),
        commit_sha=pr.head.sha[:7],
        branch=branch,
        pr_number=pr.number,
        pr_url=pr.html_url,
    )
