"""Analyse des dépendances (P1, ST-08, TASK-47 à 51).

Chaîne : find_dependency_files -> parse_versions -> find_outdated + find_vulnerable
         -> build_recommendations ; scan() enchaîne les cinq étapes (§7).

- Dernière version : API JSON de PyPI et registre npm.
- Vulnérabilités : API OSV (https://api.osv.dev/v1/query, gratuite, sans clé).
- Réseau injoignable : l'analyse est partielle, jamais d'exception (l'audit continue).

Version analysée (approximation assumée : on ne lit pas les lockfiles) :
- PyPI : seulement les versions épinglées avec ==
- npm  : version exacte, ^ ou ~ (la version de base est prise comme version installée)
Les dépendances sans version exploitable (>=, *, latest, git...) sont listées par
parse_versions avec version "" et ignorées par les analyses.
"""
import fnmatch
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests

from src.models import Finding

TIMEOUT = 8                 # secondes par requête réseau
WORKERS = 8                 # requêtes en parallèle
MAX_DEPS = 200              # garde-fou : un audit ne doit pas durer des minutes
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
             ".tox", ".mypy_cache", ".pytest_cache", "site-packages"}
NPM_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies")
OSV_URL = "https://api.osv.dev/v1/query"
OSV_ECOSYSTEM = {"pypi": "PyPI", "npm": "npm"}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_EVIDENCE_RE = re.compile(r"^(pypi|npm):(.+?)@([^@\s|]+)")      # "pypi:flask@1.0.2 | ..."
_REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$")


# --- TASK-47 : fichiers de dépendances ------------------------------------------------------
def find_dependency_files(repo_path: str) -> list[str]:
    """requirements*.txt (ou *.txt d'un dossier requirements/) et package.json.

    Les chemins renvoyés sont joints à repo_path : parse_versions peut les ouvrir tels quels.
    """
    found: list[str] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        in_requirements_dir = os.path.basename(root) == "requirements"
        for name in sorted(files):
            if (name == "package.json" or fnmatch.fnmatch(name, "requirements*.txt")
                    or (in_requirements_dir and name.endswith(".txt"))):
                found.append(os.path.join(root, name))
    return found


# --- TASK-48 : versions utilisées -----------------------------------------------------------
def _parse_requirements(text: str, rel: str) -> list[dict]:
    deps = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #")[0].split(";")[0].strip()      # commentaire inline, marqueur d'env.
        if (not line or line.startswith(("#", "-", ".", "/", "git+")) or "://" in line):
            continue                                          # options (-r, -e), URLs, chemins
        m = _REQ_RE.match(line)
        if not m:
            continue
        name, spec = m.group(1), m.group(2).strip()
        pinned = re.fullmatch(r"===?\s*([0-9][0-9A-Za-z.+!_-]*)", spec.split(",")[0].strip())
        deps.append({"ecosystem": "pypi", "name": name, "version": pinned.group(1) if pinned else "",
                     "file": rel, "line": lineno, "spec": spec})
    return deps


def _npm_version(spec: str) -> str:
    m = re.fullmatch(r"[\^~]?v?(\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?)", spec.strip())
    if not m:
        return ""
    core, _, pre = m.group(1).partition("-")
    parts = core.split(".")
    parts += ["0"] * (3 - len(parts))                        # "1.2" -> "1.2.0"
    return ".".join(parts) + (f"-{pre}" if pre else "")


def _parse_package_json(text: str, rel: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[dependencies] {rel} illisible : {exc}")
        return []
    lines = text.splitlines()
    deps = []
    for section in NPM_SECTIONS:
        for name, spec in (data.get(section) or {}).items():
            if not isinstance(spec, str):
                continue
            line = next((i for i, l in enumerate(lines, 1) if f'"{name}"' in l), 0)
            deps.append({"ecosystem": "npm", "name": name, "version": _npm_version(spec),
                         "file": rel, "line": line, "spec": spec})
    return deps


def parse_versions(files: list[str], repo_path: Optional[str] = None) -> list[dict]:
    """Une dépendance = {ecosystem, name, version, file, line, spec}.

    file est relatif à repo_path (si fourni). line et spec sont des champs en plus du contrat.
    """
    deps: list[dict] = []
    for path in files:
        rel = os.path.relpath(path, repo_path) if repo_path else path
        rel = rel.replace(os.sep, "/")
        try:
            text = Path(path).read_text(encoding="utf-8-sig", errors="replace")   # BOM Windows
        except OSError as exc:
            print(f"[dependencies] {rel} illisible : {exc}")
            continue
        deps += _parse_package_json(text, rel) if os.path.basename(path) == "package.json" \
            else _parse_requirements(text, rel)
    return deps


# --- comparaison de versions ----------------------------------------------------------------
def _num_tuple(version: str) -> tuple:
    m = re.match(r"\d+(?:\.\d+)*", (version or "").strip().lstrip("v"))
    return tuple(int(x) for x in m.group(0).split(".")) if m else ()


def _is_older(current: str, latest: str) -> bool:
    a, b = _num_tuple(current), _num_tuple(latest)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) < b + (0,) * (n - len(b))


# --- accès réseau (remplaçables en test) ----------------------------------------------------
def _latest_version(ecosystem: str, name: str) -> Optional[str]:
    """Dernière version stable, ou None si le registre est injoignable."""
    try:
        if ecosystem == "pypi":
            r = requests.get(f"https://pypi.org/pypi/{quote(name)}/json", timeout=TIMEOUT)
            return r.json()["info"]["version"] if r.status_code == 200 else None
        r = requests.get(f"https://registry.npmjs.org/{quote(name, safe='@')}/latest", timeout=TIMEOUT)
        return r.json()["version"] if r.status_code == 200 else None
    except (requests.RequestException, ValueError, KeyError):
        return None


def _osv_query(ecosystem: str, name: str, version: str) -> Optional[list[dict]]:
    """Avis OSV pour ce paquet et cette version ; None si l'API est injoignable."""
    pkg = re.sub(r"[-_.]+", "-", name).lower() if ecosystem == "pypi" else name
    try:
        r = requests.post(OSV_URL, timeout=TIMEOUT, json={
            "package": {"name": pkg, "ecosystem": OSV_ECOSYSTEM[ecosystem]}, "version": version})
        return r.json().get("vulns", []) if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def _lookup(fn, keys: list[tuple]) -> dict:
    """Interroge le réseau en parallèle ; prévient si tout a échoué (analyse partielle)."""
    if not keys:
        return {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = dict(zip(keys, pool.map(lambda k: fn(*k), keys)))
    if all(v is None for v in results.values()):
        print(f"[dependencies] {fn.__name__} : réseau injoignable, analyse partielle")
    return results


def _candidates(deps: list[dict]) -> list[dict]:
    return [d for d in deps if d.get("version")][:MAX_DEPS]


def _upgrade_text(ecosystem: str, name: str, target: str, file: str) -> str:
    if ecosystem == "pypi":
        return f"Passer {name} à {target} : modifier la version dans {file}, puis `pip install -U {name}`"
    return f"`npm install {name}@{target}` (puis committer {file} et le lockfile)"


# --- TASK-49 : dépendances obsolètes --------------------------------------------------------
def find_outdated(deps: list[dict]) -> list[Finding]:
    cand = _candidates(deps)
    latest = _lookup(_latest_version, sorted({(d["ecosystem"], d["name"]) for d in cand}))
    findings = []
    for d in cand:
        last = latest.get((d["ecosystem"], d["name"]))
        if not last or not _is_older(d["version"], last):
            continue
        major_gap = _num_tuple(d["version"])[:1] != _num_tuple(last)[:1]
        findings.append(Finding(
            rule="outdated_dependency", backlog_task="TASK-49", severity="low",
            file=d["file"], line=d.get("line", 0), source="regex", confidence=0.8,
            title=f"{d['name']} {d['version']} est obsolète (dernière version : {last})"
                  + (", version majeure en retard" if major_gap else ""),
            evidence=f"{d['ecosystem']}:{d['name']}@{d['version']} | déclaré : "
                     f"{d.get('spec') or d['version']} | dernière : {last}",
            recommendation=_upgrade_text(d["ecosystem"], d["name"], last, d["file"])))
    return findings


# --- TASK-50 : dépendances vulnérables (OSV) ------------------------------------------------
def _target_version(vulns: list[dict], current: str) -> Optional[str]:
    """Plus petite version qui corrige chaque avis, puis la plus grande de ces versions."""
    per_vuln = []
    for v in vulns:
        fixes = [ev["fixed"] for aff in v.get("affected", []) for rng in aff.get("ranges", [])
                 for ev in rng.get("events", []) if "fixed" in ev and _is_older(current, ev["fixed"])]
        if fixes:
            per_vuln.append(min(fixes, key=_num_tuple))
    return max(per_vuln, key=_num_tuple) if per_vuln else None


def find_vulnerable(deps: list[dict]) -> list[Finding]:
    cand = _candidates(deps)
    found = _lookup(_osv_query, sorted({(d["ecosystem"], d["name"], d["version"]) for d in cand}))
    findings = []
    for d in cand:
        vulns = found.get((d["ecosystem"], d["name"], d["version"]))
        if not vulns:
            continue
        ids = [v.get("id", "?") for v in vulns]
        target = _target_version(vulns, d["version"])
        summary = (vulns[0].get("summary") or "")[:100]
        findings.append(Finding(
            rule="vulnerable_dependency", backlog_task="TASK-50", severity="medium",
            file=d["file"], line=d.get("line", 0), source="osv", confidence=0.9,
            title=f"{d['name']} {d['version']} : {len(vulns)} vulnérabilité(s) connue(s)",
            evidence=f"{d['ecosystem']}:{d['name']}@{d['version']} | {', '.join(ids[:5])}"
                     + (f" | {summary}" if summary else ""),
            recommendation=(_upgrade_text(d["ecosystem"], d["name"], target, d["file"])
                            if target else f"Consulter l'avis {ids[0]} et passer à une version corrigée")))
    return findings


# --- TASK-51 : recommandations --------------------------------------------------------------
def _dep_key(f: Finding) -> Optional[tuple]:
    m = _EVIDENCE_RE.match(f.evidence)
    return (f.file, m.group(1), m.group(2)) if m else None


def build_recommendations(findings: list[Finding]) -> list[Finding]:
    """Dédoublonne, relie les problèmes d'un même paquet et trie (gravité, fichier, ligne)."""
    vulnerable = {_dep_key(f) for f in findings if f.rule == "vulnerable_dependency"} - {None}
    seen, out = set(), []
    for f in findings:
        key = (f.rule, f.file, f.evidence)
        if key in seen:
            continue
        seen.add(key)
        if f.rule == "outdated_dependency" and _dep_key(f) in vulnerable:
            f = f.model_copy(update={"recommendation": f.recommendation +
                             " (priorité : ce paquet a aussi une vulnérabilité connue, voir l'autre problème)"})
        out.append(f)
    return sorted(out, key=lambda f: (SEV_ORDER[f.severity], f.file, f.line))


def scan(repo_path: str) -> list[Finding]:
    """Enchaîne les cinq étapes ; finding_id reste vide (le runner l'attribue)."""
    files = find_dependency_files(repo_path)
    if not files:
        return []
    deps = parse_versions(files, repo_path)
    return build_recommendations(find_outdated(deps) + find_vulnerable(deps))