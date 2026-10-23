from conftest import register


def test_register_returns_token_and_user(client):
    r = client.post("/api/auth/register", json={
        "first_name": "Awa", "last_name": "Ngono",
        "phone": "+237 690 000 001", "password": "secret123",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"]
    assert body["user"]["phone"] == "+237690000001"
    assert "password_hash" not in body["user"]


def test_register_rejects_duplicate_phone(client, user):
    r = client.post("/api/auth/register", json={
        "first_name": "X", "last_name": "Y",
        "phone": user["user"]["phone"], "password": "secret123",
    })
    assert r.status_code == 409


def test_register_rejects_short_password(client):
    r = client.post("/api/auth/register", json={
        "first_name": "X", "last_name": "Y", "phone": "+237690000099", "password": "123",
    })
    assert r.status_code == 422


def test_login_with_phone_and_email(client):
    u = register(client, email="awa@example.com")
    for identifier in (u["user"]["phone"], "awa@example.com"):
        r = client.post("/api/auth/login", json={"identifier": identifier, "password": "secret123"})
        assert r.status_code == 200, identifier
        assert r.json()["access_token"]


def test_login_wrong_password_is_401(client, user):
    r = client.post("/api/auth/login", json={"identifier": user["user"]["phone"], "password": "nope-nope"})
    assert r.status_code == 401


def test_me_requires_valid_token(client, user):
    assert client.get("/api/auth/me").status_code in (401, 403)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    r = client.get("/api/auth/me", headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == user["user"]["id"]


def test_update_profile_and_change_password(client, user):
    r = client.put("/api/auth/me", json={"company_name": "Agro SA"}, headers=user["headers"])
    assert r.status_code == 200 and r.json()["company_name"] == "Agro SA"

    r = client.post("/api/auth/change-password",
                    json={"current_password": "secret123", "new_password": "newsecret1"},
                    headers=user["headers"])
    assert r.status_code == 200
    r = client.post("/api/auth/login", json={"identifier": user["user"]["phone"], "password": "newsecret1"})
    assert r.status_code == 200


def test_deactivated_account_cannot_use_token(client, user):
    assert client.delete("/api/auth/me", headers=user["headers"]).status_code == 200
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401


def test_legacy_drone_page_redirects_and_api_is_gone(client):
    for path in ("/drone", "/drone.html"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"] == "/camera"
    assert client.post("/api/drone/connect", json={}).status_code in (404, 405)


def test_register_validation_rules(client):
    base = {"first_name": "A", "last_name": "B", "phone": "+237690001234", "password": "1234567"}
    r = client.post("/api/auth/register", json=base, headers={"Accept-Language": "fr"})
    assert r.status_code == 422 and "au moins 8 caractères" in r.json()["detail"]
    r = client.post("/api/auth/register", json={**base, "password": "12345678", "first_name": "  "})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={**base, "password": "12345678", "email": "nope"})
    assert r.status_code == 422 and "Invalid email address" in r.json()["detail"]
    r = client.post("/api/auth/register", json={**base, "password": "12345678", "email": " A@B.CM "})
    assert r.status_code == 201 and r.json()["user"]["email"] == "a@b.cm"


def test_profile_fields_can_be_cleared(client, user):
    h = user["headers"]
    client.put("/api/auth/me", json={"company_name": "Agro SA", "email": "x@y.cm"}, headers=h)
    r = client.put("/api/auth/me", json={"company_name": "", "email": ""}, headers=h)
    assert r.status_code == 200
    assert r.json()["company_name"] is None and r.json()["email"] is None
    assert client.put("/api/auth/me", json={"first_name": ""}, headers=h).status_code == 422


def test_login_normalises_identifier_and_consent_at_register(client):
    r = client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "phone": "+237 690-111-222",
                                                "email": "Mixed@Case.cm", "password": "secret123",
                                                "dataset_consent": True})
    assert r.status_code == 201 and r.json()["user"]["dataset_consent"] is True
    for ident in ("+237 690 111 222", "MIXED@case.CM"):
        assert client.post("/api/auth/login", json={"identifier": ident, "password": "secret123"}).status_code == 200


def test_cameroonian_phone_normalised_at_register_and_login(client):
    from database import SessionLocal
    from models import User
    from schemas import normalize_phone

    assert normalize_phone("6 90 12 34 56") == "+237690123456"
    assert normalize_phone("00237690123456") == "+237690123456"
    assert normalize_phone("237 690-12-34-56") == "+237690123456"
    assert normalize_phone("+33612345678") == "+33612345678"

    r = client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "phone": "690 12 34 56",
                                                "password": "secret123"})
    assert r.status_code == 201 and r.json()["user"]["phone"] == "+237690123456"
    for typed in ("+237 690 12 34 56", "690123456", "00237690123456"):
        assert client.post("/api/auth/login", json={"identifier": typed, "password": "secret123"}).status_code == 200
    dup = client.post("/api/auth/register", json={"first_name": "C", "last_name": "D", "phone": "+237690123456",
                                                  "password": "secret123"})
    assert dup.status_code == 409

    # an account stored before the normalisation still signs in, and blocks duplicates
    db = SessionLocal()
    db.add(User(first_name="Old", last_name="Format", phone="677000111", password_hash=__import__("auth").hash_password("secret123")))
    db.commit()
    db.close()
    assert client.post("/api/auth/login", json={"identifier": "+237677000111", "password": "secret123"}).status_code == 200
    assert client.post("/api/auth/register", json={"first_name": "E", "last_name": "F", "phone": "677 000 111",
                                                   "password": "secret123"}).status_code == 409


def test_region_must_be_one_of_the_10_regions(client):
    """Only official region names are stored (they are published by GREEN Data)."""
    u = register(client, region="Far North")
    assert u["user"]["region"] == "Extrême-Nord"
    assert register(client, region="extreme-nord")["user"]["region"] == "Extrême-Nord"
    r = client.post("/api/auth/register", headers={"Accept-Language": "fr"}, json={
        "first_name": "A", "last_name": "B", "phone": "+237690000999", "password": "secret123",
        "region": "Quartier Bastos, chez M. Ndongo"})
    assert r.status_code == 422 and "Région du Cameroun inconnue" in r.json()["detail"]
    assert client.put("/api/auth/me", json={"region": "Mars"}, headers=u["headers"]).status_code == 422
    r = client.put("/api/auth/me", json={"region": ""}, headers=u["headers"])
    assert r.status_code == 200 and r.json()["region"] is None
