from types import SimpleNamespace

import pytest

from src import slack_app as S
from src import task_store
from src.models import Finding, Score, SecurityReport


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "repo"))


@pytest.fixture
def started(monkeypatch):
    calls = []
    monkeypatch.setattr(S.pipeline, "start_task", lambda t: calls.append(t))
    monkeypatch.setattr(S.pipeline, "_background", lambda fn, *a: fn(*a))
    return calls


class FakeClient:
    def __init__(self):
        self.posts = []

    def chat_postMessage(self, **kw):
        self.posts.append(kw)
        return {"ts": "42.1"}


def save_report(*ids):
    findings = [Finding(finding_id=i, rule="sql_injection", severity="high", file="p.py",
                        title="SQLi", evidence="TOPSECRET") for i in ids]
    report = SecurityReport(report_id="R-0001", task_id="T-0000", generated_at="x", findings=findings,
                            counts={"high": len(ids)}, score=Score(value=30, grade="E"))
    task_store.save_report(report)
    return report


@pytest.mark.parametrize("text, mode, params", [
    ("audit", "audit", {}),
    ("ANALYZE", "analyze", {}),
    ("fix F-0007", "fix", {"finding_id": "F-0007"}),
    ("fix f-0007", "fix", {"finding_id": "F-0007"}),
    ("fix the login bug", "task", {}),
    ("ask Où est l'authentification ?", "ask", {"question": "Où est l'authentification ?"}),
    ("docs readme", "docs", {"kind": "readme"}),
    ("Ajouter un champ stock au produit", "task", {}),
])
def test_parse(text, mode, params):
    cmd = S.parse_command(text)
    assert cmd.mode == mode and cmd.params == params and cmd.restore is None


def test_parse_restore():
    cmd = S.parse_command("restore t-0001 start")
    assert cmd.mode == "restore" and cmd.restore == ("T-0001", "start")


@pytest.mark.parametrize("text", ["", "help", "ask", "docs", "docs nimporte",
                                  "restore", "restore T-0001", "restore xx start"])
def test_parse_erreurs(text):
    with pytest.raises(S.UsageError):
        S.parse_command(text)


def test_launch_cree_la_tache_et_la_lance(started):
    client = FakeClient()
    task = S.launch(client, "C1", "U1", S.parse_command("Ajouter un champ stock"), "intro")
    assert task.task_id == "T-0001" and task.slack.thread_ts == "42.1"
    assert started == [task]
    assert client.posts[0]["text"] == "intro" and client.posts[1]["thread_ts"] == "42.1"


def test_launch_fix_probleme_inconnu(started):
    with pytest.raises(S.UsageError, match="F-0007"):
        S.launch(FakeClient(), "C1", "U1", S.parse_command("fix F-0007"), "intro")
    assert started == []


def test_launch_fix_refuse_le_doublon(started):
    save_report("F-0007")
    cmd = S.parse_command("fix F-0007")
    assert S.launch(FakeClient(), "C1", "U1", cmd, "intro") is not None
    assert S.launch(FakeClient(), "C1", "U1", cmd, "intro") is None
    assert len(started) == 1


def test_blocs_d_audit():
    report = save_report(*[f"F-{i:04d}" for i in range(1, 8)])
    blocks = S.build_audit_blocks(SimpleNamespace(task_id="T-0003"), report)
    buttons = [b["accessory"] for b in blocks if "accessory" in b]
    assert len(buttons) == 5
    assert buttons[0]["action_id"] == "fix_finding" and buttons[0]["value"] == "F-0001"
    flat = str(blocks)
    assert "30/100" in flat and "2 autres" in flat
    assert "TOPSECRET" not in flat                          # evidence jamais affichée