import pytest

from src import task_store as ts
from src.models import Finding, SlackInfo, SecurityReport, Score  # Score/SecurityReport : après la PR models

SLACK = SlackInfo(channel_id="C1", thread_ts="1.1", user_id="U1")


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DB_PATH", str(tmp_path / "test.db"))


def test_ids_increment_and_branch():
    t1 = ts.create_task("task", "Ajouter un champ stock", {}, SLACK)
    t2 = ts.create_task("audit", "audit", {}, SLACK)
    assert t1.task_id == "T-0001" and t2.task_id == "T-0002"
    assert t1.branch == "agent/T-0001-ajouter-un-champ-stock"
    assert t2.branch is None            # lecture seule : pas de branche


def test_slug_removes_accents():
    t = ts.create_task("fix", "Corriger l'injection SQL é à", {"finding_id": "F-0007"}, SLACK)
    assert t.branch == "agent/T-0001-corriger-l-injection-sql-e-a"
    assert t.params == {"finding_id": "F-0007"}


def test_update_status_and_fields():
    t = ts.create_task("task", "x", {}, SLACK)
    ts.update_status(t.task_id, ts.AWAITING_REVIEW, jira_key="AGT-12", revision=1)
    got = ts.get_task(t.task_id)
    assert got.jira_key == "AGT-12" and got.revision == 1
    assert ts.get_status(t.task_id) == ts.AWAITING_REVIEW


def test_update_rejects_bad_input():
    t = ts.create_task("task", "x", {}, SLACK)
    with pytest.raises(ValueError):
        ts.update_status(t.task_id, "nimporte")
    with pytest.raises(ValueError):
        ts.update_status(t.task_id, ts.FAILED, mode="audit")   # champ non modifiable
    with pytest.raises(KeyError):
        ts.update_status("T-9999", ts.FAILED)

def test_list_tasks_most_recent_first():
    ts.create_task("task", "a", {}, SLACK)
    ts.create_task("task", "b", {}, SLACK)
    assert [t.task_id for t in ts.list_tasks()] == ["T-0002", "T-0001"]


def test_save_report_and_get_finding_latest_wins():
    def report(rid, title):
        f = Finding(finding_id="F-0007", rule="sql_injection", severity="high",
                    file="a.py", title=title)
        return SecurityReport(report_id=rid, task_id="T-0001",
                              generated_at="2026-12-01T10:00:00Z", findings=[f],
                              counts={"high": 1}, score=Score(value=90, grade="A"))
    ts.save_report(report("R-0001", "ancien"))
    ts.save_report(report("R-0002", "récent"))
    assert ts.get_finding("F-0007").title == "récent"
    with pytest.raises(KeyError):
        ts.get_finding("F-9999")