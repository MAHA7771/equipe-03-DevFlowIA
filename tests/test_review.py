from src.models import AgentResult, AgentTests, DiffReport, FileDiff, SlackInfo, Task
from src.review import build_review_blocks, reject_modal


def _task():
    return Task(task_id="T-0001", mode="fix", description="d",
                slack=SlackInfo(channel_id="C1", thread_ts="1.0", user_id="U1"), repo_path=".")


def _result(passed=True, explanation="Pourquoi c'est grave"):
    return AgentResult(task_id="T-0001", status="success", summary="Requête paramétrée.",
                       explanation=explanation, tests=AgentTests(ran=True, passed=passed, output="3 passed"))


def _diff(text="diff --git a/x b/x"):
    return DiffReport(task_id="T-0001", files=[FileDiff(path="backend/app/products.py", additions=8, deletions=1)],
                      diff_text=text)


def test_boutons_et_ids_du_contrat():
    blocks = build_review_blocks(_task(), _result(), _diff())
    actions = [b for b in blocks if b["type"] == "actions"][0]["elements"]
    assert [(a["action_id"], a["value"]) for a in actions] == [("approve_task", "T-0001"), ("reject_task", "T-0001")]


def test_explication_presente_seulement_en_mode_fix():
    avec = str(build_review_blocks(_task(), _result(), _diff()))
    sans = str(build_review_blocks(_task(), _result(explanation=None), _diff()))
    assert "Pourquoi c'est grave" in avec and "Pourquoi c'est grave" not in sans


def test_aucun_bloc_ne_depasse_3000_caracteres():
    blocks = build_review_blocks(_task(), _result(), _diff("x" * 10000))
    for b in blocks:
        if b["type"] == "section":
            assert len(b["text"]["text"]) <= 3000


def test_tests_echoues_affiches():
    assert "échoués" in str(build_review_blocks(_task(), _result(passed=False), _diff()))


def test_modale_conforme_au_contrat():
    v = reject_modal("T-0001")
    assert v["callback_id"] == "reject_feedback_modal"
    assert v["blocks"][0]["block_id"] == "feedback"
    assert v["blocks"][0]["element"]["action_id"] == "feedback_input"
    assert v["private_metadata"] == "T-0001"
