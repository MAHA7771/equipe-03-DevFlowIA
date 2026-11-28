import subprocess

import pytest

from src import git_ops
from src.git_ops import commit_and_push, get_diff, prepare_branch, run_git


def sh(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """Faux GitHub : un dépôt bare local avec une branche main."""
    bare = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    sh("git", "init", "--bare", "-b", "main", str(bare))
    sh("git", "init", "-b", "main", str(seed))
    (seed / "app.py").write_text("print('v1')\n")
    sh("git", "add", "-A", cwd=seed)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init", cwd=seed)
    sh("git", "remote", "add", "origin", str(bare), cwd=seed)
    sh("git", "push", "origin", "main", cwd=seed)
    monkeypatch.setenv("GIT_REMOTE_URL", str(bare))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return bare


def test_prepare_branch_clone_et_creation(tmp_path, remote):
    repo = str(tmp_path / "workspace" / "shop")
    prepare_branch(repo, "agent/T-0001-test", "main")
    assert run_git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "agent/T-0001-test"


def test_prepare_branch_reutilise_la_branche(tmp_path, remote):
    repo = str(tmp_path / "ws")
    prepare_branch(repo, "agent/T-0001-test", "main")
    (tmp_path / "ws" / "x.txt").write_text("travail en cours")
    prepare_branch(repo, "agent/T-0001-test", "main")          # 2e appel : ne perd rien
    assert (tmp_path / "ws" / "x.txt").exists()


def test_get_diff_inclut_les_fichiers_nouveaux(tmp_path, remote):
    repo = str(tmp_path / "ws")
    prepare_branch(repo, "agent/T-0001-test", "main")
    (tmp_path / "ws" / "app.py").write_text("print('v2')\nprint('v3')\n")
    (tmp_path / "ws" / "nouveau.py").write_text("x = 1\n")
    diff = get_diff(repo, "T-0001")
    paths = {f.path for f in diff.files}
    assert paths == {"app.py", "nouveau.py"}
    assert "nouveau.py" in diff.diff_text


def test_get_diff_tronque_a_3000(tmp_path, remote):
    repo = str(tmp_path / "ws")
    prepare_branch(repo, "agent/T-0001-test", "main")
    (tmp_path / "ws" / "gros.txt").write_text("ligne\n" * 5000)
    assert len(get_diff(repo, "T-0001").diff_text) < 3100


def test_commit_and_push_refuse_main(tmp_path, remote):
    repo = str(tmp_path / "ws")
    prepare_branch(repo, "agent/T-0001-test", "main")
    with pytest.raises(ValueError):
        commit_and_push(repo, "main", "msg")
    with pytest.raises(ValueError):
        commit_and_push(repo, "feature/autre", "msg")


def test_commit_and_push_ok(tmp_path, remote):
    repo = str(tmp_path / "ws")
    prepare_branch(repo, "agent/T-0001-test", "main")
    (tmp_path / "ws" / "app.py").write_text("print('corrige')\n")
    sha = commit_and_push(repo, "agent/T-0001-test", "fix: test")
    assert len(sha) >= 7
    branches = subprocess.run(["git", "branch", "--list"], cwd=remote, capture_output=True, text=True).stdout
    assert "agent/T-0001-test" in branches
    assert "main" in branches


def test_commit_and_push_sans_changement(tmp_path, remote):
    repo = str(tmp_path / "ws")
    prepare_branch(repo, "agent/T-0001-test", "main")
    with pytest.raises(RuntimeError):
        commit_and_push(repo, "agent/T-0001-test", "vide")


def test_le_token_est_masque_dans_les_erreurs(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_SECRET123")
    assert "ghp_SECRET123" not in git_ops._mask("erreur avec ghp_SECRET123 dedans")
