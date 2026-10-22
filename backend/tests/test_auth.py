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
