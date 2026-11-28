from types import SimpleNamespace

import pytest

from src import pipeline as P
from src import task_store
from src.models import (AgentResult, AgentTests, Checkpoint, DiffReport, FileDiff, Finding,
                        PRResult, ReviewDecision, SlackInfo)

SLACK = SlackInfo(channel_id="C1", thread_ts="1.1", user_id="U1")


def agent_ok(task):
    return AgentResult(task_id=task.task_id, status="success", summary="ok",
                       files_changed=["a.py"], tests=AgentTests(ran=True, passed=True), iterations=1)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "repo"))
    monkeypatch.setenv("BASE_BRANCH", "main")
    e = SimpleNamespace(log=[], agent=[], said=[], fail=False)

    def rec(name):
        return lambda *a, **k: e.log.append((name, *a[1:2]))

    monkeypatch.setattr(P.jira_client, "create_issue", lambda t: (e.log.append(("jira.create",)), "AGT-1")[1])
    monkeypatch.setattr(P.jira_client, "transition", lambda k, target: e.log.append(("jira.transition", target)))
    monkeypatch.setattr(P.jira_client, "add_comment", lambda k, text: e.log.append(("jira.comment", text)))
    monkeypatch.setattr(P.jira_client, "add_label", lambda k, label: e.log.append(("jira.label", label)))
    monkeypatch.setattr(P.git_ops, "prepare_branch", lambda repo, branch, base: e.log.append(("git.prepare", branch)))
    monkeypatch.setattr(P.git_ops, "run_git", lambda *a, **k: "")
    monkeypatch.setattr(P.git_ops, "get_diff", lambda repo, tid: DiffReport(
        task_id=tid, files=[FileDiff(path="a.py", additions=2, deletions=0)], diff_text="diff --git"))

    def commit(repo, branch, msg):
        e.log.append(("git.commit", branch))
        return "abc1234"
    monkeypatch.setattr(P.git_ops, "commit_and_push", commit)
    monkeypatch.setattr(P.github_client, "open_pull_request", lambda branch, title, body: (
        e.log.append(("pr.open", branch)),
        PRResult(task_id="T-0001", commit_sha="abc1234", branch=branch, pr_number=12,
                 pr_url="https://github.com/o/r/pull/12"))[1])

    def create_cp(repo, tid, label):
        e.log.append(("cp.create", label))
        return Checkpoint(checkpoint_id=f"{tid}/001", task_id=tid, label=label, ref="r",
                          commit="c", files_changed=1, created_at="x")
    monkeypatch.setattr(P.checkpoints, "create_checkpoint", create_cp)
    monkeypatch.setattr(P.checkpoints, "list_checkpoints", lambda repo, tid: [Checkpoint(
        checkpoint_id=f"{tid}/002", task_id=tid, label="agent_done_r0", ref="r", commit="c",
        files_changed=1, created_at="x")])
    monkeypatch.setattr(P.checkpoints, "restore_checkpoint", lambda repo, cid: e.log.append(("cp.restore", cid)))
    monkeypatch.setattr(P.review, "post_review_request", lambda t, r, d: e.log.append(("review.post",)))

    def fake_agent(task, on_checkpoint):
        e.agent.append((task.revision, task.feedback))
        if e.fail:
            raise RuntimeError("boom")
        on_checkpoint("iter-1")
        return agent_ok(task)
    monkeypatch.setattr(P, "run_agent", fake_agent)
    monkeypatch.setattr(P, "run_security_audit", lambda repo: [
        Finding(finding_id="F-0001", rule="exposed_secret", severity="critical", file="a.env",
                title="Secret", evidence="TOPSECRET"),
        Finding(finding_id="F-0002", rule="sql_injection", severity="high", file="p.py", title="SQLi"),
        Finding(finding_id="F-0003", rule="xss", severity="high", file="p.jsx", title="XSS")])
    monkeypatch.setattr(P, "_background", lambda fn, *a: fn(*a))      # synchrone en test
    monkeypatch.setattr(P, "_say", lambda task, text: e.said.append(text))
    monkeypatch.setattr(P, "_say_audit", lambda task, report: e.said.append("audit"))
    return e


def new_task(mode="task", desc="Ajouter un champ stock", params=None):
    return task_store.create_task(mode, desc, params or {}, SLACK)


def decision(kind, feedback=None):
    return ReviewDecision(task_id="T-0001", decision=kind, feedback=feedback, reviewer_slack_id="U1")


def of(e, name):
    return [c[1] for c in e.log if c[0] == name]


def test_flux_task_jusqu_a_la_revue(env):
    P.start_task(new_task())
    assert task_store.get_status("T-0001") == "awaiting_review"
    assert of(env, "cp.create") == ["start", "iter-1", "agent_done_r0"]
    assert of(env, "jira.transition") == ["done"]
    assert ("review.post",) in env.log


def test_flux_audit(env):
    P.start_task(new_task("audit", "audit"))
    assert task_store.get_status("T-0001") == "completed"
    assert task_store.get_finding("F-0002").title == "SQLi"
    comment = of(env, "jira.comment")[0]
    assert "55/100" in comment and "note D" in comment      # 100 - 25 - 10 - 10
    assert "TOPSECRET" not in comment                        # evidence jamais envoyé
    assert ("review.post",) not in env.log and not of(env, "cp.create")


def test_approbation_ouvre_la_pr(env):
    P.start_task(new_task())
    P.on_review_decision(decision("approved"))
    assert task_store.get_status("T-0001") == "pr_opened"
    assert of(env, "git.commit") == ["agent/T-0001-ajouter-un-champ-stock"]
    assert any("pull/12" in c for c in of(env, "jira.comment"))


def test_rejet_puis_retravail(env):
    P.start_task(new_task())
    P.on_review_decision(decision("rejected", "Ajoute stock >= 0"))
    assert env.agent == [(0, None), (1, "Ajoute stock >= 0")]
    assert of(env, "jira.transition") == ["done", "in_progress", "done"]
    assert "agent_done_r1" in of(env, "cp.create")
    assert task_store.get_status("T-0001") == "awaiting_review"
    assert task_store.get_task("T-0001").revision == 1


def test_echec_restaure_et_etiquette(env):
    env.fail = True
    P.start_task(new_task())
    assert task_store.get_status("T-0001") == "failed"
    assert ("cp.restore", "T-0001/002") in env.log
    assert "agentfailed" in of(env, "jira.label")
    assert any("boom" in c for c in of(env, "jira.comment"))


def test_double_clic_une_seule_pr(env):
    P.start_task(new_task())
    P.on_review_decision(decision("approved"))
    P.on_review_decision(decision("approved"))
    assert len(of(env, "git.commit")) == 1


def test_decision_ignoree_si_rien_a_valider(env):
    P.start_task(new_task("audit", "audit"))                 # completed : pas de validation
    P.on_review_decision(decision("approved"))
    assert not of(env, "git.commit")