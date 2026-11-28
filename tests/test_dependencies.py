import json

import pytest
import requests

from src.security.scanners import dependencies as D


def write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture
def repo(tmp_path):
    write(tmp_path, "backend/requirements.txt", (
        "# dépendances\n"
        "flask==1.0.2\n"
        "requests>=2.0\n"
        "pydantic[email]==2.5.0  # commentaire\n"
        "uvicorn==0.30.0; python_version >= '3.8'\n"
        "numpy==1.*\n"
        "-r base.txt\n"
        "git+https://github.com/x/y.git\n"
        "\n"))
    write(tmp_path, "frontend/package.json", json.dumps({
        "dependencies": {"react": "^18.2.0", "lodash": "4.17.20", "@scope/pkg": "~1.2",
                         "left-pad": ">=1.0.0", "other": "*", "local": "workspace:*"},
        "devDependencies": {"vite": "^5.0.0"}}, indent=2))
    write(tmp_path, "frontend/node_modules/x/package.json", "{}")
    write(tmp_path, ".venv/requirements.txt", "evil==1.0\n")
    return tmp_path


def by_name(deps):
    return {d["name"]: d for d in deps}


def test_find_files_ignore_node_modules_et_venv(repo):
    rel = sorted(p.replace(str(repo), "").replace("\\", "/").lstrip("/")
                 for p in D.find_dependency_files(str(repo)))
    assert rel == ["backend/requirements.txt", "frontend/package.json"]


def test_find_files_dossier_requirements(tmp_path):
    write(tmp_path, "requirements/base.txt", "a==1\n")
    write(tmp_path, "requirements-dev.txt", "b==1\n")
    write(tmp_path, "notes.txt", "c==1\n")
    names = sorted(p.rsplit("requirements", 1)[1] for p in D.find_dependency_files(str(tmp_path)))
    assert len(names) == 2


def test_parse_requirements(repo):
    deps = by_name(D.parse_versions(D.find_dependency_files(str(repo)), str(repo)))
    assert deps["flask"] == {"ecosystem": "pypi", "name": "flask", "version": "1.0.2",
                             "file": "backend/requirements.txt", "line": 2, "spec": "==1.0.2"}
    assert deps["pydantic"]["version"] == "2.5.0"           # extras et commentaire ignorés
    assert deps["uvicorn"]["version"] == "0.30.0"           # marqueur d'environnement ignoré
    assert deps["requests"]["version"] == ""                # >= : non épinglé
    assert deps["numpy"]["version"] == ""                   # joker
    assert "base.txt" not in str(deps) and "y.git" not in str(deps)


def test_parse_package_json(repo):
    deps = by_name(D.parse_versions(D.find_dependency_files(str(repo)), str(repo)))
    assert deps["react"]["version"] == "18.2.0" and deps["react"]["ecosystem"] == "npm"
    assert deps["lodash"]["version"] == "4.17.20"
    assert deps["@scope/pkg"]["version"] == "1.2.0"         # complété à 3 chiffres
    assert deps["vite"]["version"] == "5.0.0"               # devDependencies incluses
    assert deps["left-pad"]["version"] == "" and deps["other"]["version"] == ""
    assert deps["local"]["version"] == ""
    assert deps["react"]["line"] > 0 and deps["react"]["file"] == "frontend/package.json"


def test_parse_ignore_un_json_invalide(tmp_path):
    path = write(tmp_path, "package.json", "{pas du json")
    assert D.parse_versions([path], str(tmp_path)) == []


def test_parse_gere_le_bom_windows(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_bytes(b"\xef\xbb\xbfflask==1.0.2\n")
    assert D.parse_versions([str(path)], str(tmp_path))[0]["name"] == "flask"


@pytest.mark.parametrize("current, latest, older", [
    ("1.0.2", "3.0.0", True), ("1.9.0", "1.10.0", True), ("2.0", "2.0.0", False),
    ("3.0.0", "2.9.9", False), ("2.0.0rc1", "2.0.0", False), ("abc", "1.0", False)])
def test_is_older(current, latest, older):
    assert D._is_older(current, latest) is older


def dep(name="flask", version="1.0.2", eco="pypi", file="requirements.txt", line=3):
    return {"ecosystem": eco, "name": name, "version": version, "file": file, "line": line, "spec": ""}


def test_find_outdated(monkeypatch):
    latest = {("pypi", "flask"): "3.0.0", ("pypi", "uvicorn"): "0.30.0", ("npm", "react"): None}
    monkeypatch.setattr(D, "_latest_version", lambda eco, name: latest.get((eco, name)))
    deps = [dep(), dep("uvicorn", "0.30.0"), dep("react", "18.2.0", "npm"), dep("requests", "")]
    findings = D.find_outdated(deps)
    assert len(findings) == 1                               # à jour, injoignable et non épinglé : ignorés
    f = findings[0]
    assert (f.rule, f.severity, f.backlog_task, f.finding_id) == ("outdated_dependency", "low", "TASK-49", "")
    assert "3.0.0" in f.title and "majeure" in f.title and f.line == 3
    assert "pip install -U flask" in f.recommendation


def test_find_vulnerable_cible_la_plus_petite_version_corrigee(monkeypatch):
    vulns = [{"id": "GHSA-1", "summary": "Faille A", "affected": [{"ranges": [{"events": [
                 {"introduced": "0"}, {"fixed": "1.0.1"}, {"fixed": "1.0.3"}, {"fixed": "2.0.0"}]}]}]},
             {"id": "CVE-2", "affected": [{"ranges": [{"events": [{"fixed": "1.1.0"}]}]}]}]
    calls = []
    monkeypatch.setattr(D, "_osv_query", lambda eco, name, v: (calls.append(1), vulns if name == "flask" else [])[1])
    findings = D.find_vulnerable([dep(), dep("uvicorn", "0.30.0"), dep("flask", "1.0.2", file="other.txt")])
    assert len(findings) == 2                               # flask dans 2 fichiers, uvicorn sain
    f = findings[0]
    assert (f.rule, f.severity, f.backlog_task, f.source) == ("vulnerable_dependency", "medium", "TASK-50", "osv")
    assert "2 vulnérabilité" in f.title and "GHSA-1" in f.evidence and "Faille A" in f.evidence
    assert "Passer flask à 1.1.0" in f.recommendation       # max(min(1.0.3, 2.0.0), 1.1.0) ; 1.0.1 est déjà dépassée
    assert len(calls) == 2                                  # une requête par (paquet, version) unique


def test_find_vulnerable_sans_version_corrigee(monkeypatch):
    monkeypatch.setattr(D, "_osv_query", lambda *a: [{"id": "GHSA-9"}])
    f = D.find_vulnerable([dep()])[0]
    assert "GHSA-9" in f.recommendation


def test_reseau_injoignable_donne_zero_probleme(monkeypatch, capsys):
    monkeypatch.setattr(D, "_latest_version", lambda *a: None)
    monkeypatch.setattr(D, "_osv_query", lambda *a: None)
    assert D.find_outdated([dep()]) == [] and D.find_vulnerable([dep()]) == []
    assert "réseau injoignable" in capsys.readouterr().out


def test_build_recommendations_relie_trie_et_dedoublonne(monkeypatch):
    monkeypatch.setattr(D, "_latest_version", lambda *a: "3.0.0")
    monkeypatch.setattr(D, "_osv_query", lambda eco, name, v: [{"id": "GHSA-1"}] if name == "flask" else [])
    deps = [dep("uvicorn", "0.1.0", line=1), dep("flask", "1.0.2", line=9)]
    findings = D.find_outdated(deps) + D.find_vulnerable(deps)
    out = D.build_recommendations(findings + findings)      # doublons volontaires
    assert [f.rule for f in out] == ["vulnerable_dependency", "outdated_dependency", "outdated_dependency"]
    assert out[0].severity == "medium"
    flask_outdated = next(f for f in out if f.rule == "outdated_dependency" and "flask" in f.title)
    assert "vulnérabilité connue" in flask_outdated.recommendation
    uvicorn_outdated = next(f for f in out if "uvicorn" in f.title)
    assert "vulnérabilité" not in uvicorn_outdated.recommendation


def test_scan_de_bout_en_bout(repo, monkeypatch):
    monkeypatch.setattr(D, "_latest_version", lambda eco, name: "99.0.0" if name == "lodash" else None)
    monkeypatch.setattr(D, "_osv_query", lambda eco, name, v: [{"id": "GHSA-L"}] if name == "lodash" else [])
    findings = D.scan(str(repo))
    assert {f.rule for f in findings} == {"vulnerable_dependency", "outdated_dependency"}
    assert all(f.file == "frontend/package.json" and f.finding_id == "" for f in findings)
    assert D.scan(str(repo / "backend" / "nope")) == []


class FakeResp:
    def __init__(self, code, data):
        self.status_code, self._data = code, data

    def json(self):
        return self._data


def test_latest_version_pypi_et_npm_scope(monkeypatch):
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        return FakeResp(200, {"info": {"version": "3.0.0"}} if "pypi" in url else {"version": "4.1.0"})

    monkeypatch.setattr(D.requests, "get", fake_get)
    assert D._latest_version("pypi", "flask") == "3.0.0"
    assert D._latest_version("npm", "@scope/pkg") == "4.1.0"
    assert urls[1] == "https://registry.npmjs.org/@scope%2Fpkg/latest"


def test_acces_reseau_ne_leve_jamais(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("hors ligne")
    monkeypatch.setattr(D.requests, "get", boom)
    monkeypatch.setattr(D.requests, "post", boom)
    assert D._latest_version("pypi", "flask") is None
    assert D._osv_query("pypi", "flask", "1.0") is None
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: FakeResp(404, None))
    assert D._latest_version("npm", "x") is None


def test_osv_normalise_le_nom_pypi(monkeypatch):
    sent = {}
    monkeypatch.setattr(D.requests, "post", lambda url, json, timeout: (sent.update(json), FakeResp(200, {"vulns": []}))[1])
    D._osv_query("pypi", "Flask_Cors", "1.0")
    assert sent["package"] == {"name": "flask-cors", "ecosystem": "PyPI"}