"""TASK-46 : détecter les problèmes d'autorisation (P3, Should).

Analyse les routes FastAPI : une route admin doit exiger un utilisateur ET un rôle.
"""
import re
from pathlib import Path

from src.models import Finding

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "workspace"}

RE_ROUTE = re.compile(r"^\s*@\w+\.(get|post|put|delete|patch)\(\s*[\"']([^\"']*)[\"']")
RE_AUTH_DEP = re.compile(r"Depends\(\s*\w*(user|admin|auth|token|role)\w*", re.I)
RE_ROLE = re.compile(r"require_admin|get_current_admin|admin_required|require_role|role_required|is_admin"
                     r"|[\"']role[\"']|\.role\b|\brole\s*[!=]=", re.I)
RE_PUBLIC_PATH = re.compile(r"login|register|signup|token|health|docs", re.I)
RE_ROUTER_DEPS = re.compile(r"APIRouter\([^)]*dependencies\s*=", re.S)


def _f(rel, line, sev, title, evidence, reco, conf) -> Finding:
    return Finding(rule="authz_issue", backlog_task="TASK-46", severity=sev, file=rel, line=line,
                   title=title, evidence=evidence.strip()[:200], recommendation=reco,
                   confidence=conf, source="regex")


def _route_blocks(lines: list[str]):
    """Découpe le fichier : (n° de ligne, méthode, chemin, texte décorateur+signature, texte corps)."""
    i = 0
    while i < len(lines):
        m = RE_ROUTE.match(lines[i])
        if not m:
            i += 1
            continue
        start = i
        j = i
        while j < len(lines) and not re.match(r"\s*(async\s+)?def\s", lines[j]):
            j += 1
        k = j
        while k < len(lines) and not lines[k].rstrip().endswith(":"):
            k += 1
        header = "\n".join(lines[start:k + 1])
        body_end = k + 1
        while body_end < len(lines) and (not lines[body_end].strip() or lines[body_end][0] in " \t"):
            body_end += 1
        yield start + 1, m.group(1), m.group(2), header, "\n".join(lines[k + 1:body_end])
        i = body_end


def scan(repo_path: str) -> list[Finding]:
    root = Path(repo_path)
    findings: list[Finding] = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if SKIP_DIRS & set(path.relative_to(root).parts) or "/tests/" in f"/{rel}" or path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        router_protected = bool(RE_ROUTER_DEPS.search(text))

        for line_no, method, route, header, body in _route_blocks(lines):
            is_admin = "admin" in route.lower() or path.stem == "admin"
            has_auth = router_protected or bool(RE_AUTH_DEP.search(header))
            has_role = bool(RE_ROLE.search(header + "\n" + body)) or (router_protected and "admin" in text.lower() and bool(RE_ROLE.search(text)))
            evidence = lines[line_no - 1]

            if is_admin and not has_auth:
                findings.append(_f(rel, line_no, "high", f"Route admin sans authentification ({method.upper()} {route})",
                                   evidence, "Ajouter Depends(require_admin) sur la route.", 0.9))
            elif is_admin and not has_role:
                findings.append(_f(rel, line_no, "high", f"Route admin sans vérification du rôle ({method.upper()} {route})",
                                   evidence, "Vérifier user['role'] == 'admin' (par ex. Depends(require_admin)).", 0.8))
            elif method in {"post", "put", "delete", "patch"} and not has_auth and not RE_PUBLIC_PATH.search(route):
                findings.append(_f(rel, line_no, "medium", f"Route d'écriture sans authentification ({method.upper()} {route})",
                                   evidence, "Exiger un utilisateur connecté avec Depends(get_current_user).", 0.5))
    return findings
