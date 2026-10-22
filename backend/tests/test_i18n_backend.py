"""Server messages follow Accept-Language / ?lang= (lot 3.5)."""

import json
import re
from pathlib import Path

import i18n


def test_http_error_translated(client, user):
    h = dict(user["headers"])
    assert client.get("/api/analysis/999", headers=h).json()["detail"] == "Analysis not found."
    h["Accept-Language"] = "fr-CM,fr;q=0.9,en;q=0.8"
    assert client.get("/api/analysis/999", headers=h).json()["detail"] == "Analyse introuvable."
    assert client.get("/api/analysis/999?lang=en", headers=h).json()["detail"] == "Analysis not found."


def test_unauthenticated_fr(client):
    r = client.get("/api/auth/me", headers={"Accept-Language": "fr"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Session invalide ou expirée. Veuillez vous reconnecter."


def test_validation_error_flattened_and_translated(client):
    r = client.post("/api/auth/register", json={"first_name": "A"}, headers={"Accept-Language": "fr"})
    assert r.status_code == 422
    body = r.json()
    assert isinstance(body["detail"], str)
    assert body["detail"].startswith("Veuillez vérifier le formulaire")
    assert "mot de passe : champ obligatoire" in body["detail"]
    assert "[object" not in body["detail"]
    r = client.post("/api/auth/register", json={"first_name": "A"})
    assert r.json()["detail"].startswith("Please check the form") and "password: Field required" in r.json()["detail"]


def test_pattern_message(client, user):
    h = {**user["headers"], "Accept-Language": "fr"}
    assert client.get("/api/diseases/nope", headers=h).json()["detail"] == "Maladie « nope » introuvable."


def test_every_raised_message_has_a_french_translation():
    """Each literal English detail raised by the backend is in the catalogue."""
    root = Path(__file__).resolve().parent.parent
    missing = []
    for py in list(root.glob("*.py")) + list((root / "routers").glob("*.py")):
        src = py.read_text(encoding="utf-8")
        for m in re.finditer(r'(?:detail=|GeometryError\(|msg = )f?"([^"]+)"', src):
            msg = m.group(1)
            if msg.endswith(" ") and m.end() < len(src):   # implicitly concatenated string: take the next one
                nxt = re.match(r'\s*f?"([^"]+)"', src[m.end():])
                msg += nxt.group(1) if nxt else ""
            if "{" in msg:
                sample = re.sub(r"\{[^}]+\}", "1", msg)
                if i18n.translate(sample, "fr") == sample:
                    missing.append(f"{py.name}: {msg}")
            elif i18n.translate(msg, "fr") == msg:
                missing.append(f"{py.name}: {msg}")
    assert missing == [], json.dumps(missing, indent=1, ensure_ascii=False)
