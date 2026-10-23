"""Weather proxy: disabled cleanly without a key; tips and OWM language follow the request."""

import routers.weather_router as w


def test_weather_disabled_without_key(client, user):
    r = client.get("/api/weather/current", headers={**user["headers"], "Accept-Language": "fr"})
    assert r.status_code == 503
    assert r.json()["detail"] == "Le service météo n'est pas configuré sur ce serveur."


def test_agro_tip_codes_and_language():
    assert w._agro_tip(25, 60, 500, "fr")["code"] == "wet"
    tip = w._agro_tip(25, 90, 800, "fr")
    assert tip["code"] == "humid" and "90 %" in tip["message"] and "Humidité" in tip["message"]
    assert w._agro_tip(38, 40, 800, "en")["message"].startswith("Intense heat (38 °C)")
    assert w._agro_tip(25, 60, 800, "en")["code"] == "ok"


def test_region_resolves_to_capital():
    assert w._resolve_coords(None, None, None, "Littoral")["label"] == "Douala, Littoral"
    assert w._resolve_coords(None, None, None, None)["label"] == "Yaoundé, Centre"


def test_owm_called_in_request_language(client, user, monkeypatch):
    seen = {}

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"name": "Douala", "main": {"temp": 30, "humidity": 70}, "weather": [{"id": 800, "description": "ciel dégagé"}]}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params):
            seen.update(params)
            return FakeResp()

    monkeypatch.setattr(w, "WEATHER_API_KEY", "k")
    monkeypatch.setattr(w.httpx, "AsyncClient", FakeClient)
    r = client.get("/api/weather/current?region=Littoral", headers={**user["headers"], "Accept-Language": "fr"})
    assert r.status_code == 200 and seen["lang"] == "fr"
    assert r.json()["agro_tip"]["code"] == "ok"


def test_provider_errors_never_log_the_api_key(client, user, monkeypatch, caplog):
    secret = "abc123secretkey"

    class FailingClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params):
            req = w.httpx.Request("GET", url, params=params)
            raise w.httpx.HTTPStatusError("boom", request=req, response=w.httpx.Response(401, request=req))

    monkeypatch.setattr(w, "WEATHER_API_KEY", secret)
    monkeypatch.setattr(w.httpx, "AsyncClient", FailingClient)
    with caplog.at_level("ERROR"):
        r = client.get("/api/weather/current?region=Littoral", headers=user["headers"])
    assert r.status_code == 502
    assert "HTTP 401" in caplog.text and secret not in caplog.text and "appid" not in caplog.text
