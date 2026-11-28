"""Security Score (§6.9) : calcul d'après score_rules.json.

value = max(floor, start - somme(poids[severity] x nombre de problèmes))
Seules les règles de sécurité comptent : les règles de qualité (bug, complexity,
bad_practice, duplicate_code) sont listées dans "ignored_rules" et n'ont aucun effet.
"""
import json
from pathlib import Path

from src.models import Finding

RULES_PATH = Path(__file__).with_name("score_rules.json")
SEVERITIES = ("critical", "high", "medium", "low")


def load_rules() -> dict:
    """Relu à chaque appel : on peut ajuster le JSON sans redémarrer ni toucher au code."""
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def is_security_finding(finding: Finding, rules: dict | None = None) -> bool:
    rules = rules or load_rules()
    return finding.rule not in rules["ignored_rules"]


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    """Comptage par niveau, pour le champ "counts" du SecurityReport.

    Seuls les problèmes de sécurité sont comptés ; les autres sont affichés à part.
    """
    rules = load_rules()
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        if is_security_finding(f, rules):
            counts[f.severity] += 1
    return counts


def grade_for(value: int, rules: dict | None = None) -> str:
    rules = rules or load_rules()
    for step in sorted(rules["grades"], key=lambda g: g["min"], reverse=True):
        if value >= step["min"]:
            return step["grade"]
    return rules["grades"][-1]["grade"]       # sécurité : ne devrait jamais arriver (floor = 0)


def compute_score(findings: list[Finding]) -> dict:
    """Renvoie {"value": 67, "grade": "C"} (§7)."""
    rules = load_rules()
    counts = count_by_severity(findings)
    penalty = sum(rules["weights"].get(sev, 0) * n for sev, n in counts.items())
    value = max(rules["floor"], rules["start"] - penalty)
    return {"value": value, "grade": grade_for(value, rules)}