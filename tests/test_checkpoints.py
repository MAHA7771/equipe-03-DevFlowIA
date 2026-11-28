import subprocess

import pytest

from src.checkpoints import (KEEP, create_checkpoint, list_checkpoints,
                             restore_checkpoint)
from src.git_ops import run_git


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(r)], check=True, capture_output=True)
    (r / "app.py").write_text("v1\n")
    (r / "vieux.py").write_text("a supprimer plus tard\n")
    run_git(str(r), "add", "-A")
    run_git(str(r), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init")
    return str(r), r


def test_create_ne_bouge_pas_la_branche(repo):
    path, r = repo
    head_avant = run_git(path, "rev-parse", "HEAD")
    (r / "app.py").write_text("v2\n")
    cp = create_checkpoint(path, "T-0001", "start")
    assert run_git(path, "rev-parse", "HEAD") == head_avant
    assert cp.checkpoint_id == "T-0001/001"
    assert cp.ref == "refs/agent/checkpoints/T-0001/001"
    assert cp.files_changed == 1


def test_restore_remet_les_fichiers(repo):
    path, r = repo
    create_checkpoint(path, "T-0001", "start")
    (r / "app.py").write_text("MODIFIE\n")
    (r / "nouveau.py").write_text("ajoute par l'agent\n")
    restore_checkpoint(path, "T-0001/001")
    assert (r / "app.py").read_text() == "v1\n"
    assert not (r / "nouveau.py").exists()


def test_restore_par_etiquette(repo):
    path, r = repo
    create_checkpoint(path, "T-0001", "start")
    (r / "app.py").write_text("v2\n")
    create_checkpoint(path, "T-0001", "iter-1")
    (r / "app.py").write_text("v3\n")
    restore_checkpoint(path, "T-0001/start")
    assert (r / "app.py").read_text() == "v1\n"
    restore_checkpoint(path, "T-0001/iter-1")
    assert (r / "app.py").read_text() == "v2\n"


def test_restore_remet_un_fichier_supprime_et_supprime_un_ajout(repo):
    path, r = repo
    (r / "app.py").write_text("v2\n")
    create_checkpoint(path, "T-0001", "iter-1")          # état : app.py=v2, vieux.py présent
    (r / "vieux.py").unlink()
    (r / "app.py").write_text("v9\n")
    restore_checkpoint(path, "T-0001/001")
    assert (r / "vieux.py").exists()
    assert (r / "app.py").read_text() == "v2\n"


def test_restore_fichier_absent_du_checkpoint(repo):
    path, r = repo
    (r / "vieux.py").unlink()
    create_checkpoint(path, "T-0001", "iter-1")          # état : vieux.py supprimé
    (r / "vieux.py").write_text("revenu\n")
    restore_checkpoint(path, "T-0001/001")
    assert not (r / "vieux.py").exists()


def test_liste_du_plus_recent_au_plus_ancien(repo):
    path, r = repo
    for i in range(3):
        (r / "app.py").write_text(f"v{i}\n")
        create_checkpoint(path, "T-0001", f"iter-{i}")
    labels = [c.label for c in list_checkpoints(path, "T-0001")]
    assert labels == ["iter-2", "iter-1", "iter-0"]


def test_garde_les_10_derniers_mais_toujours_start(repo):
    path, r = repo
    create_checkpoint(path, "T-0001", "start")
    for i in range(14):
        (r / "app.py").write_text(f"v{i}\n")
        create_checkpoint(path, "T-0001", f"iter-{i}")
    cps = list_checkpoints(path, "T-0001")
    labels = [c.label for c in cps]
    assert "start" in labels
    assert len(cps) == KEEP + 1                      # 10 récents + start conservé
    assert "iter-13" in labels and "iter-0" not in labels


def test_taches_independantes(repo):
    path, r = repo
    create_checkpoint(path, "T-0001", "start")
    create_checkpoint(path, "T-0002", "start")
    assert len(list_checkpoints(path, "T-0001")) == 1
    assert len(list_checkpoints(path, "T-0002")) == 1


def test_restore_inconnu(repo):
    path, _ = repo
    with pytest.raises(Exception):
        restore_checkpoint(path, "T-0009/start")
