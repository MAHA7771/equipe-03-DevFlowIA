from src.quality.analyze import analyze_code
from src.security.scanners import auth, authz, misconfig


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_misconfig(tmp_path):
    write(tmp_path, "backend/app/main.py",
          "app.add_middleware(CORSMiddleware, allow_origins=['*'])\nDEBUG = True\nrequests.get(u, verify=False)\n")
    write(tmp_path, ".env", "X=1\n")
    titres = {f.title for f in misconfig.scan(str(tmp_path))}
    assert "CORS ouvert à toutes les origines" in titres
    assert "Mode debug activé" in titres
    assert "Vérification TLS désactivée" in titres
    assert "Fichier .env non ignoré par Git" in titres
    for f in misconfig.scan(str(tmp_path)):
        assert f.rule == "misconfiguration" and f.finding_id == "" and f.backlog_task == "TASK-44"


def test_misconfig_env_ignore_ok(tmp_path):
    write(tmp_path, ".env", "X=1\n")
    write(tmp_path, ".gitignore", ".env\n")
    assert misconfig.scan(str(tmp_path)) == []


def test_misconfig_code_propre(tmp_path):
    write(tmp_path, "main.py", "allow_origins=['http://localhost:5173']\nDEBUG = os.getenv('DEBUG') == '1'\n")
    assert misconfig.scan(str(tmp_path)) == []


def test_auth_detections_et_secret_masque(tmp_path):
    write(tmp_path, "backend/app/auth.py", (
        "import hashlib, jwt\n"
        "SECRET_KEY = 'secret'\n"
        "h = hashlib.md5(pw.encode())\n"
        "token = jwt.encode({'sub': 1}, SECRET_KEY, algorithm='HS256')\n"
        "if user.password == body.password:\n    pass\n"))
    res = auth.scan(str(tmp_path))
    titres = {f.title for f in res}
    assert {"Hachage faible (MD5/SHA-1)", "JWT créé sans expiration",
            "Mot de passe comparé en clair", "Clé de signature JWT faible"} <= titres
    secret = [f for f in res if f.title == "Clé de signature JWT faible"][0]
    assert "secr****" in secret.evidence and "'secret'" not in secret.evidence


def test_auth_code_sain(tmp_path):
    write(tmp_path, "auth.py", (
        "import jwt, bcrypt\nSECRET_KEY = os.environ['JWT_SECRET']\n"
        "payload = {'sub': 1, 'exp': now + 3600}\ntoken = jwt.encode(payload, SECRET_KEY, algorithm='HS256')\n"
        "ok = bcrypt.checkpw(pw, h)\n"))
    assert auth.scan(str(tmp_path)) == []


def test_authz(tmp_path):
    write(tmp_path, "backend/app/admin.py", (
        "from fastapi import APIRouter, Depends\nrouter = APIRouter()\n\n"
        "@router.get('/api/admin/stats')\ndef stats():\n    return {}\n\n"
        "@router.get('/api/admin/users')\ndef users(user=Depends(get_current_user)):\n    return []\n\n"
        "@router.delete('/api/admin/products/{id}')\ndef rm(id: int, admin=Depends(require_admin)):\n    return {}\n"))
    write(tmp_path, "backend/app/cart.py", (
        "@router.post('/api/cart/items')\ndef add():\n    return {}\n\n"
        "@router.post('/api/auth/login')\ndef login():\n    return {}\n"))
    res = {f.title: f for f in authz.scan(str(tmp_path))}
    assert "Route admin sans authentification (GET /api/admin/stats)" in res
    assert "Route admin sans vérification du rôle (GET /api/admin/users)" in res
    assert "Route d'écriture sans authentification (POST /api/cart/items)" in res
    assert len(res) == 3                      # la route protégée et le login ne sont pas signalés
    assert all(f.rule == "authz_issue" for f in res.values())


def test_analyze(tmp_path):
    bloc = "".join(f"    total_{i} = compute_something_long_name({i}) + other_value_{i}\n" for i in range(8))
    write(tmp_path, "a.py", "def f(x=[]):\n" + bloc + "    try:\n        pass\n    except:\n        pass\n")
    write(tmp_path, "b.py", "def g():\n" + bloc)
    branches = "".join(f"    if x == {i}:\n        return {i}\n" for i in range(14))
    write(tmp_path, "c.py", "def h(x):\n" + branches + "    return None\n")
    res = analyze_code(str(tmp_path))
    rules = {f.rule for f in res}
    assert {"duplicate_code", "bad_practice", "complexity"} <= rules
    assert all(f.finding_id == "" for f in res)
