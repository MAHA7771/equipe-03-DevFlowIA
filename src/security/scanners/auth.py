"""TASK-45 : détecter les problèmes d'authentification (P3, Should)."""
import re
from pathlib import Path

from src.models import Finding

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "workspace"}
EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
WEAK_SECRETS = {"secret", "changeme", "password", "123456", "test", "dev", "key", "jwt", "admin"}

RE_WEAK_HASH = re.compile(r"\bhashlib\.(md5|sha1)\s*\(")
RE_PLAIN_COMPARE = re.compile(r"\.password\s*==\s*\w|\w\s*==\s*\w+\.password\b|\[\s*[\"']password[\"']\s*\]\s*==")
RE_JWT_ENCODE = re.compile(r"\bjwt\.(encode|sign)\s*\(")
RE_JWT_BYPASS = re.compile(r"algorithms\s*=\s*\[\s*[\"']none[\"']|verify_signature[\"']?\s*[:=]\s*False|verify_exp[\"']?\s*[:=]\s*False", re.I)
RE_SECRET_ASSIGN = re.compile(r"\b(SECRET_KEY|JWT_SECRET|JWT_SECRET_KEY)\s*=\s*[\"']([^\"']*)[\"']")


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in EXTENSIONS and not (SKIP_DIRS & set(p.relative_to(root).parts)):
            yield p


def _mask_value(value: str) -> str:
    return value[:4] + "****"


def _f(rel, line, sev, title, evidence, reco, conf=0.7) -> Finding:
    return Finding(rule="auth_issue", backlog_task="TASK-45", severity=sev, file=rel, line=line,
                   title=title, evidence=evidence.strip()[:200], recommendation=reco,
                   confidence=conf, source="regex")


def scan(repo_path: str) -> list[Finding]:
    root = Path(repo_path)
    findings: list[Finding] = []
    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in f"/{rel}" or path.name.startswith("test_"):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith(("#", "//")):
                continue
            if RE_WEAK_HASH.search(line):
                findings.append(_f(rel, n, "high", "Hachage faible (MD5/SHA-1)", line,
                                   "Hacher les mots de passe avec bcrypt ou argon2.", 0.85))
            if RE_PLAIN_COMPARE.search(line):
                findings.append(_f(rel, n, "high", "Mot de passe comparé en clair", line,
                                   "Stocker un hash et le vérifier avec bcrypt.checkpw.", 0.6))
            if RE_JWT_BYPASS.search(line):
                findings.append(_f(rel, n, "high", "Vérification du JWT désactivée", line,
                                   "Toujours vérifier la signature et l'expiration du token.", 0.9))
            if RE_JWT_ENCODE.search(line):
                window = "\n".join(lines[max(0, n - 12):n + 3])      # payload construit juste avant
                if not re.search(r"[\"']exp[\"']|\bexp\s*=|expires?", window, re.I):
                    findings.append(_f(rel, n, "high", "JWT créé sans expiration", line,
                                       "Ajouter une claim 'exp' (par ex. 60 minutes).", 0.65))
            m = RE_SECRET_ASSIGN.search(line)
            if m and (m.group(2).lower() in WEAK_SECRETS or len(m.group(2)) < 16) and m.group(2):
                masked = line.replace(m.group(2), _mask_value(m.group(2)))   # jamais le secret en clair
                findings.append(_f(rel, n, "high", "Clé de signature JWT faible", masked,
                                   "Utiliser une clé aléatoire d'au moins 32 octets, lue depuis .env.", 0.75))
    return findings