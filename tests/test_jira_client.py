import pytest

from src import jira_client as jc
from src.models import SlackInfo, Task


def make_task() -> Task:
    return Task(task_id="T-0001", mode="task", description="Ajouter un champ stock",
                slack=SlackInfo(channel_id="C1", thread_ts="1.1", user_id="U1"),
                branch="agent/T-0001-x", repo_path=".")


class Resp:
    def __init__(self, code, data=None):
        self.status_code = code
        self._data = data
        self.text = "x" if data is not None else ""

    def json(self):
        return self._data


class FakeJira:
    """Simule les 4 endpoints utilisés, avec un statut qui évolue."""
    def __init__(self, initial="En cours"):
        self.status = initial
        self.calls = []
        self.transitions = [{"id": "11", "to": {"name": "En cours"}},
                            {"id": "21", "to": {"name": "Terminé"}}]

    def __call__(self, method, url, **kw):
        self.calls.append((method, url.split("/rest/api/2")[1], kw.get("json")))
        path = url.split("/rest/api/2")[1]
        if method == "POST" and path == "/issue":
            return Resp(201, {"key": "AGT-12"})
        if method == "GET" and path == "/issue/AGT-12":
            return Resp(200, {"fields": {"status": {"name": self.status}}})
        if method == "GET" and path.endswith("/transitions"):
            return Resp(200, {"transitions": self.transitions})
        if method == "POST" and path.endswith("/transitions"):
            tid = kw["json"]["transition"]["id"]
            self.status = next(t["to"]["name"] for t in self.transitions if t["id"] == tid)
            return Resp(204)
        if path.endswith("/comment") or method == "PUT":
            return Resp(201, {"id": "1"})
        return Resp(404, {"error": path})


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://exemple.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "a@b.tn")
    monkeypatch.setenv("JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AGT")
    monkeypatch.setenv("JIRA_STATUS_IN_PROGRESS", "En cours")
    monkeypatch.setenv("JIRA_STATUS_DONE", "Terminé")
    fake = FakeJira()
    monkeypatch.setattr(jc.requests, "request", fake)
    return fake


def test_mode_factice_sans_url(monkeypatch, capsys):
    monkeypatch.setenv("JIRA_BASE_URL", "")
    key = jc.create_issue(make_task())
    jc.transition(key, "done")
    jc.add_comment(key, "bonjour")
    assert key.startswith("AGT-FAKE")
    assert "[jira:factice]" in capsys.readouterr().out


def test_create_issue_renvoie_la_cle(live):
    assert jc.create_issue(make_task()) == "AGT-12"
    post = next(c for c in live.calls if c[0] == "POST" and c[1] == "/issue")
    assert post[2]["fields"]["project"] == {"key": "AGT"}
    assert post[2]["fields"]["summary"].startswith("[T-0001]")


def test_create_issue_passe_en_cours_si_besoin(live):
    live.status = "Terminé"                      # statut initial inattendu
    jc.create_issue(make_task())
    assert live.status == "En cours"


def test_transition_vers_done(live):
    jc.transition("AGT-12", "done")
    assert live.status == "Terminé"


def test_transition_idempotente(live):
    jc.transition("AGT-12", "in_progress")       # déjà « En cours »
    assert not any(c[1].endswith("/transitions") and c[0] == "POST" for c in live.calls)


def test_transition_inconnue(live):
    live.transitions = [{"id": "11", "to": {"name": "En cours"}}]
    with pytest.raises(jc.JiraError):
        jc.transition("AGT-12", "done")
    with pytest.raises(ValueError):
        jc.transition("AGT-12", "nimporte")


def test_commentaire_tronque(live):
    jc.add_comment("AGT-12", "x" * 40000)
    sent = next(c for c in live.calls if c[1].endswith("/comment"))[2]["body"]
    assert len(sent) < 32767 and sent.endswith("[...tronqué]")


def test_erreur_http_levee(live, monkeypatch):
    monkeypatch.setattr(jc.requests, "request", lambda *a, **k: Resp(401, {"e": 1}))
    with pytest.raises(jc.JiraError, match="401"):
        jc.add_comment("AGT-12", "x")