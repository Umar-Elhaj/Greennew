"""GreenBot: ownership of the analysis context (T2), language, disabled without key."""

import routers.chatbot_router as bot
from conftest import jpeg_bytes


def _session(client, h):
    return client.post("/api/chat/sessions", json={}, headers=h).json()["id"]


def _upload(client, h):
    return client.post("/api/camera/upload", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")},
                       headers=h).json()["analysis_id"]


def test_disabled_without_key_is_explained(client, user):
    sid = _session(client, user["headers"])
    r = client.post(f"/api/chat/sessions/{sid}/messages", json={"content": "Bonjour"},
                    headers={**user["headers"], "Accept-Language": "fr"})
    assert r.status_code == 503
    assert r.json()["detail"] == "GreenBot n'est pas configuré sur ce serveur."


def test_other_users_analysis_is_never_used(client, user, other_user, fake_model, monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "_call_llm", lambda *a, **k: calls.append((a, k)) or "ok")
    foreign = _upload(client, other_user["headers"])
    sid = _session(client, user["headers"])
    r = client.post(f"/api/chat/sessions/{sid}/messages", json={"content": "Hi", "analysis_id": foreign},
                    headers=user["headers"])
    assert r.status_code == 404
    assert calls == []
    # and it was not stored on the user's message either
    msgs = client.get(f"/api/chat/sessions/{sid}", headers=user["headers"]).json()["messages"]
    assert all(m["analysis_id"] != foreign for m in msgs)


def test_own_analysis_context_and_language(client, user, fake_model, monkeypatch):
    captured = {}

    def fake_llm(history, rag, analysis_ctx, lang, user_ctx):
        captured.update(analysis=analysis_ctx, lang=lang, user=user_ctx)
        return "Réponse"

    monkeypatch.setattr(bot, "_call_llm", fake_llm)
    aid = _upload(client, user["headers"])
    sid = _session(client, user["headers"])
    r = client.post(f"/api/chat/sessions/{sid}/messages", json={"content": "Que faire ?", "analysis_id": aid},
                    headers={**user["headers"], "Accept-Language": "fr"})
    assert r.status_code == 200 and r.json()["content"] == "Réponse"
    assert captured["lang"] == "fr"
    assert "PROBABLE disease" in captured["analysis"] and "Maize leaf blight" in captured["analysis"]
    assert "Region of Cameroon" in captured["user"]


def test_system_prompt_language_rule():
    assert "Answer in French" in bot.SYSTEM_PROMPT.format(language_rule=bot.LANGUAGE_RULES["fr"])


def test_empty_message_rejected(client, user):
    sid = _session(client, user["headers"])
    assert client.post(f"/api/chat/sessions/{sid}/messages", json={"content": ""},
                       headers=user["headers"]).status_code == 422
