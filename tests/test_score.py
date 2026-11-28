import pytest

from src.models import Finding
from src.security.score import compute_score, count_by_severity


def f(rule: str, severity: str) -> Finding:
    return Finding(rule=rule, severity=severity, file="a.py", title="t")


def test_exemple_du_contrat():
    # §6.9 : 2 high, 3 medium, 1 low -> 100 - 20 - 12 - 1 = 67, note C
    findings = (
        [f("sql_injection", "high")] * 2
        + [f("misconfiguration", "medium")] * 3
        + [f("outdated_dependency", "low")]
    )
    assert compute_score(findings) == {"value": 67, "grade": "C"}


def test_aucun_probleme():
    assert compute_score([]) == {"value": 100, "grade": "A"}


def test_un_secret_critique_coute_25():
    assert compute_score([f("exposed_secret", "critical")]) == {"value": 75, "grade": "B"}


def test_plancher_a_zero():
    findings = [f("exposed_secret", "critical")] * 10      # 250 points de pénalité
    assert compute_score(findings) == {"value": 0, "grade": "E"}


def test_regles_de_qualite_sans_effet():
    findings = [
        f("bug", "high"), f("complexity", "medium"),
        f("bad_practice", "low"), f("duplicate_code", "medium"),
    ]
    assert compute_score(findings) == {"value": 100, "grade": "A"}


def test_counts_ignorent_la_qualite():
    findings = [f("xss", "high"), f("bug", "high"), f("exposed_secret", "critical")]
    assert count_by_severity(findings) == {"critical": 1, "high": 1, "medium": 0, "low": 0}


@pytest.mark.parametrize("nb_low, value, grade", [
    (10, 90, "A"), (11, 89, "B"),
    (25, 75, "B"), (26, 74, "C"),
    (40, 60, "C"), (41, 59, "D"),
    (60, 40, "D"), (61, 39, "E"),
])
def test_limites_des_notes(nb_low, value, grade):
    findings = [f("outdated_dependency", "low")] * nb_low
    assert compute_score(findings) == {"value": value, "grade": grade}