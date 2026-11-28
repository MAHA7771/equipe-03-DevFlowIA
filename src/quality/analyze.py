"""Analyse de qualité du code (P3, Could) : /agent analyze.

Règles : complexity (radon), duplicate_code (fenêtres de lignes), bad_practice (regex),
bug (LLM, optionnel : voir _ask_llm).
"""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from src.models import Finding

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "workspace"}
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx"}
COMPLEXITY_LIMIT = 10          # au-dessus : signalé
WINDOW = 6                     # nombre de lignes comparées pour les doublons
MIN_WINDOW_CHARS = 120         # ignore les blocs triviaux (imports, accolades)

BAD_PRACTICES = [
    (re.compile(r"^\s*except\s*:\s*(#.*)?$"), "except nu : masque toutes les erreurs",
     "Attraper une exception précise (except ValueError:)."),
    (re.compile(r"def\s+\w+\(.*=\s*(\[\]|\{\}|set\(\))\s*[,)]"), "Argument par défaut mutable",
     "Utiliser None puis créer la liste ou le dict dans la fonction."),
    (re.compile(r"[!=]=\s*None\b"), "Comparaison à None avec == ou !=", "Utiliser 'is None' / 'is not None'."),
]


def _iter_files(root: Path, exts: set[str]):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in exts and not (SKIP_DIRS & set(p.relative_to(root).parts)):
            yield p


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _complexity(root: Path) -> list[Finding]:
    try:
        from radon.complexity import cc_visit
    except ImportError:
        return []
    out = []
    for p in _iter_files(root, {".py"}):
        try:
            blocks = cc_visit(_read(p))
        except SyntaxError:
            continue
        for b in blocks:
            if b.complexity > COMPLEXITY_LIMIT:
                out.append(Finding(
                    rule="complexity", backlog_task="", severity="medium" if b.complexity > 15 else "low",
                    file=p.relative_to(root).as_posix(), line=b.lineno,
                    title=f"Fonction trop complexe : {b.name} (complexité {b.complexity})",
                    evidence=f"def {b.name}(...)", confidence=0.95, source="radon",
                    recommendation="Découper la fonction en fonctions plus petites."))
    return out


def _bad_practices(root: Path) -> list[Finding]:
    out = []
    for p in _iter_files(root, {".py"}):
        for n, line in enumerate(_read(p).splitlines(), 1):
            for rx, title, reco in BAD_PRACTICES:
                if rx.search(line):
                    out.append(Finding(rule="bad_practice", severity="low",
                                       file=p.relative_to(root).as_posix(), line=n, title=title,
                                       evidence=line.strip()[:200], recommendation=reco,
                                       confidence=0.8, source="regex"))
    return out


def _duplicates(root: Path) -> list[Finding]:
    seen: dict[str, tuple[str, int]] = {}
    reported_until: dict[str, int] = defaultdict(int)
    out = []
    for p in _iter_files(root, CODE_EXT):
        rel = p.relative_to(root).as_posix()
        norm = [(i + 1, l.strip()) for i, l in enumerate(_read(p).splitlines()) if l.strip()]
        for k in range(len(norm) - WINDOW + 1):
            chunk = norm[k:k + WINDOW]
            text = "\n".join(l for _, l in chunk)
            if len(text) < MIN_WINDOW_CHARS:
                continue
            h = hashlib.md5(text.encode()).hexdigest()
            start = chunk[0][0]
            if h not in seen:
                seen[h] = (rel, start)
            elif seen[h] != (rel, start) and start > reported_until[rel]:
                orig_file, orig_line = seen[h]
                reported_until[rel] = chunk[-1][0]
                out.append(Finding(
                    rule="duplicate_code", severity="low", file=rel, line=start,
                    title=f"Code dupliqué (voir {orig_file}:{orig_line})",
                    evidence=chunk[0][1][:200], confidence=0.7, source="regex",
                    recommendation="Extraire le bloc commun dans une fonction réutilisable."))
    return out


def _ask_llm(prompt: str) -> str:
    """Appelle le LLM de P2. À brancher : P2 doit exposer src.agent.llm_client.complete(prompt) -> str.
    Sans cette fonction, la détection de bugs par LLM est simplement ignorée."""
    try:
        from src.agent.llm_client import complete
    except (ImportError, AttributeError):
        return ""
    try:
        return complete(prompt)
    except Exception:
        return ""


def _llm_bugs(root: Path, max_files: int = 3) -> list[Finding]:
    files = sorted(_iter_files(root, CODE_EXT), key=lambda p: p.stat().st_size, reverse=True)[:max_files]
    out = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        prompt = (
            "Relis ce fichier et liste les bugs potentiels. Réponds UNIQUEMENT par un tableau JSON "
            '[{"line": int, "title": str, "recommendation": str}] ([] s\'il n\'y en a pas).\n'
            f"Fichier {rel} :\n{_read(p)[:6000]}")
        raw = _ask_llm(prompt)
        match = re.search(r"\[.*\]", raw, re.S)
        if not match:
            continue
        try:
            items = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        for it in items[:5]:
            if isinstance(it, dict) and it.get("title"):
                out.append(Finding(rule="bug", severity="medium", file=rel, line=int(it.get("line") or 0),
                                   title=str(it["title"])[:150], recommendation=str(it.get("recommendation", ""))[:200],
                                   confidence=0.5, source="llm"))
    return out


def analyze_code(repo_path: str) -> list[Finding]:
    root = Path(repo_path)
    return _complexity(root) + _duplicates(root) + _bad_practices(root) + _llm_bugs(root)
