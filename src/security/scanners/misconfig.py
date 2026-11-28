"""TASK-44 : détecter les mauvaises configurations (P3, Should)."""
import re
from pathlib import Path

from src.models import Finding

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "workspace"}
EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".yml", ".yaml", ".json", ".toml", ".ini"}

# (regex, titre, recommandation)
RULES = [
    (re.compile(r"\b(DEBUG|debug)\s*=\s*True\b"),
     "Mode debug activé", "Désactiver le debug en production (lire la valeur depuis l'environnement)."),
    (re.compile(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]"),
     "CORS ouvert à toutes les origines", "Lister explicitement les origines autorisées."),
    (re.compile(r"Access-Control-Allow-Origin[\"']?\s*[:,]\s*[\"']\*[\"']"),
     "CORS ouvert à toutes les origines", "Renvoyer uniquement les origines de confiance."),
    (re.compile(r"\bverify\s*=\s*False\b"),
     "Vérification TLS désactivée", "Laisser verify=True (ou fournir le bon certificat)."),
    (re.compile(r"\bcheck_hostname\s*=\s*False\b"),
     "Vérification du nom d'hôte TLS désactivée", "Garder check_hostname activé."),
    (re.compile(r"\b(secure|httponly|httpOnly)\s*[=:]\s*(False|false)\b"),
     "Cookie sans drapeau de sécurité", "Activer Secure et HttpOnly sur les cookies de session."),
    (re.compile(r"\ballow_credentials\s*=\s*True\b.*\ballow_origins\s*=\s*\[\s*[\"']\*[\"']"),
     "CORS avec identifiants et origine *", "Ne jamais combiner credentials et origine *."),
]


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in EXTENSIONS and not (SKIP_DIRS & set(p.relative_to(root).parts)):
            yield p


def _finding(rel: str, line: int, title: str, evidence: str, reco: str, conf: float) -> Finding:
    return Finding(rule="misconfiguration", backlog_task="TASK-44", severity="medium",
                   file=rel, line=line, title=title, evidence=evidence.strip()[:200],
                   recommendation=reco, confidence=conf, source="regex")


def scan(repo_path: str) -> list[Finding]:
    root = Path(repo_path)
    findings: list[Finding] = []

    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in f"/{rel}" or path.name.startswith("test_"):
            continue                                      # les tests ne sont pas une config de prod
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith(("#", "//")):
                continue
            for rx, title, reco in RULES:
                if rx.search(line):
                    findings.append(_finding(rel, n, title, line, reco, 0.8))

    # Fichier .env présent mais non ignoré par Git
    if (root / ".env").is_file():
        gitignore = root / ".gitignore"
        ignored = gitignore.is_file() and re.search(
            r"^\s*/?\.env\s*$", gitignore.read_text(encoding="utf-8", errors="ignore"), re.M)
        if not ignored:
            findings.append(_finding(".env", 1, "Fichier .env non ignoré par Git",
                                     "(contenu non affiché)",
                                     "Ajouter .env à .gitignore et révoquer les secrets déjà exposés.", 0.9))
    return findings
