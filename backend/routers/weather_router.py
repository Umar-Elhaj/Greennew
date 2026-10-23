# ============================================================
# GREEN App — Weather Router
#
# Proxies OpenWeatherMap API calls so the API key stays
# server-side and is never exposed to the browser.
#
# Endpoints:
#   GET /api/weather/current   — current conditions
#   GET /api/weather/forecast  — 5-day / 3-hour forecast
# ============================================================

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import get_current_user
from config import WEATHER_API_KEY, OPENWEATHER_BASE_URL
from i18n import request_lang
from models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["Weather"])

# Cameroon region → coordinates mapping (fallback when no GPS)
CAMEROON_COORDS = {
    "yaounde":   {"lat": 3.8480,  "lon": 11.5021, "label": "Yaoundé, Centre"},
    "douala":    {"lat": 4.0511,  "lon": 9.7679,  "label": "Douala, Littoral"},
    "bafoussam": {"lat": 5.4737,  "lon": 10.4175, "label": "Bafoussam, Ouest"},
    "garoua":    {"lat": 9.3017,  "lon": 13.3921, "label": "Garoua, Nord"},
    "maroua":    {"lat": 10.5910, "lon": 14.3158, "label": "Maroua, Extrême-Nord"},
    "bertoua":   {"lat": 4.5833,  "lon": 13.6833, "label": "Bertoua, Est"},
    "buea":      {"lat": 4.1597,  "lon": 9.2416,  "label": "Buea, Sud-Ouest"},
    "ebolowa":   {"lat": 2.9000,  "lon": 11.1500, "label": "Ebolowa, Sud"},
    "ngaoundere":{"lat": 7.3265,  "lon": 13.5840, "label": "Ngaoundéré, Adamaoua"},
    "bamenda":   {"lat": 5.9527,  "lon": 10.1460, "label": "Bamenda, Nord-Ouest"},
}

DEFAULT_CITY = "yaounde"

# Region of Cameroon (as stored on users/parcels) → regional capital
REGION_CAPITALS = {
    "Adamaoua": "ngaoundere", "Centre": "yaounde", "Est": "bertoua", "Extrême-Nord": "maroua",
    "Littoral": "douala", "Nord": "garoua", "Nord-Ouest": "bamenda", "Ouest": "bafoussam",
    "Sud": "ebolowa", "Sud-Ouest": "buea",
}

# Agronomic tips: code → message per language ({temp}, {humidity} filled in)
AGRO_TIPS = {
    "wet": {
        "en": "Wet weather: high risk of fungal spread (late blight, early blight). "
              "Inspect your crops and consider a preventive treatment.",
        "fr": "Temps humide : risque élevé de propagation des champignons (mildiou, alternariose). "
              "Inspectez vos cultures et envisagez un traitement préventif.",
    },
    "humid": {
        "en": "High humidity ({humidity} %): favourable to fungi and bacteria. Check cassava and tomato.",
        "fr": "Humidité élevée ({humidity} %) : conditions favorables aux champignons et aux bactéries. "
              "Surveillez le manioc et la tomate.",
    },
    "hot": {
        "en": "Intense heat ({temp} °C): possible water stress on sensitive crops. Make sure irrigation is sufficient.",
        "fr": "Forte chaleur ({temp} °C) : stress hydrique possible sur les cultures sensibles. "
              "Assurez une irrigation suffisante.",
    },
    "cool": {
        "en": "Cool temperatures ({temp} °C): slower growth. Watch for frost risk at altitude.",
        "fr": "Températures fraîches ({temp} °C) : croissance ralentie. Surveillez le risque de gel en altitude.",
    },
    "ok": {
        "en": "Favourable growing conditions: no immediate weather alert.",
        "fr": "Conditions favorables aux cultures : aucune alerte météo immédiate.",
    },
}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _require_key():
    if not WEATHER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="The weather service is not configured on this server.",
        )


def _resolve_coords(city: Optional[str], lat: Optional[float], lon: Optional[float],
                    region: Optional[str] = None) -> dict:
    """Return OWM query params and a display label."""
    if lat is not None and lon is not None:
        return {"params": {"lat": lat, "lon": lon}, "label": f"{lat:.4f}°N, {lon:.4f}°E"}

    if not city and region in REGION_CAPITALS:
        city = REGION_CAPITALS[region]
    key = (city or DEFAULT_CITY).lower().strip()
    preset = CAMEROON_COORDS.get(key)
    if preset:
        return {"params": {"lat": preset["lat"], "lon": preset["lon"]}, "label": preset["label"]}

    # Pass city name directly to OWM (handles any city worldwide)
    return {"params": {"q": f"{city},CM"}, "label": city}


def _agro_tip(temp: float, humidity: float, weather_id: int, lang: str = "en") -> dict:
    """
    Agronomic risk level and advice from the current conditions.
    weather_id = OWM condition code (2xx thunder, 3xx drizzle, 5xx rain, 8xx clear/cloud…)
    """
    if 200 <= weather_id < 600:
        level, code = "warning", "wet"
    elif humidity > 85:
        level, code = "warning", "humid"
    elif temp > 36:
        level, code = "caution", "hot"
    elif temp < 14:
        level, code = "info", "cool"
    else:
        level, code = "ok", "ok"
    message = AGRO_TIPS[code]["fr" if lang == "fr" else "en"].format(temp=f"{temp:.0f}", humidity=humidity)
    return {"level": level, "code": code, "message": message}


def _format_current(raw: dict, label: str, lang: str = "en") -> dict:
    """Flatten OWM /weather response into a clean dict."""
    main    = raw.get("main", {})
    wind    = raw.get("wind", {})
    weather = raw.get("weather", [{}])[0]
    sys     = raw.get("sys", {})

    temp     = main.get("temp",       0.0)
    humidity = main.get("humidity",   0)
    w_id     = weather.get("id",      800)

    tip = _agro_tip(temp, humidity, w_id, lang)

    return {
        "city":        raw.get("name", label),
        "label":       label,
        "country":     sys.get("country", "CM"),
        "temp":        round(temp, 1),
        "feels_like":  round(main.get("feels_like", temp), 1),
        "temp_min":    round(main.get("temp_min", temp), 1),
        "temp_max":    round(main.get("temp_max", temp), 1),
        "humidity":    humidity,
        "pressure":    main.get("pressure", 0),
        "wind_speed":  round(wind.get("speed", 0) * 3.6, 1),   # m/s → km/h
        "wind_deg":    wind.get("deg", 0),
        "clouds":      raw.get("clouds", {}).get("all", 0),
        "weather_id":  w_id,
        "description": weather.get("description", "").capitalize(),
        "icon":        weather.get("icon", "01d"),
        "sunrise":     sys.get("sunrise"),
        "sunset":      sys.get("sunset"),
        "agro_tip":    tip,
    }


def _format_forecast(raw: dict, label: str, lang: str = "en") -> list:
    """
    Convert OWM /forecast (3h steps) to a list of daily summaries.
    Groups by date, picks the midday (12:00) entry or the first of the day.
    """
    from collections import defaultdict

    days: dict = defaultdict(list)
    for item in raw.get("list", []):
        date_str = item["dt_txt"][:10]
        days[date_str].append(item)

    result = []
    for date_str in sorted(days.keys())[:5]:
        entries = days[date_str]
        # Pick midday entry if available, else first
        midday = next(
            (e for e in entries if "12:00:00" in e["dt_txt"]),
            entries[len(entries) // 2],
        )
        main    = midday.get("main", {})
        weather = midday.get("weather", [{}])[0]
        wind    = midday.get("wind", {})
        temp    = main.get("temp", 0)
        humidity = main.get("humidity", 0)
        w_id    = weather.get("id", 800)

        result.append({
            "date":        date_str,
            "temp_max":    round(max(e["main"]["temp"] for e in entries), 1),
            "temp_min":    round(min(e["main"]["temp"] for e in entries), 1),
            "temp":        round(temp, 1),
            "humidity":    humidity,
            "wind_speed":  round(wind.get("speed", 0) * 3.6, 1),
            "weather_id":  w_id,
            "description": weather.get("description", "").capitalize(),
            "icon":        weather.get("icon", "01d"),
            "agro_tip":    _agro_tip(temp, humidity, w_id, lang),
        })
    return result


# ─────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────

def _describe(exc: Exception) -> str:
    """Error type and HTTP status only: the request URL carries the API key (appid)."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


@router.get("/current", summary="Current weather for a city, a region or GPS coordinates")
async def get_current_weather(
    request: Request,
    city: Optional[str]  = Query(None, description="City (e.g. Yaoundé, Douala…)"),
    region: Optional[str]= Query(None, description="Region of Cameroon (its capital is used)"),
    lat:  Optional[float]= Query(None, description="GPS latitude"),
    lon:  Optional[float]= Query(None, description="GPS longitude"),
    current_user: User   = Depends(get_current_user),
):
    """
    Current conditions from OpenWeatherMap, in the request language.
    Priority: GPS coordinates > city > region > Yaoundé.
    """
    _require_key()
    lang = request_lang(request)
    resolved = _resolve_coords(city, lat, lon, region)

    params = {
        **resolved["params"],
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang":  lang,
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{OPENWEATHER_BASE_URL}/weather", params=params)
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"City not found: {city}")
            r.raise_for_status()
            return _format_current(r.json(), resolved["label"], lang)
    except httpx.HTTPError as exc:
        logger.error("[Weather] OpenWeather error: %s", _describe(exc))
        raise HTTPException(status_code=502, detail="The weather service is unavailable.")


@router.get("/forecast", summary="5-day forecast (daily summary)")
async def get_forecast(
    request: Request,
    city: Optional[str]  = Query(None),
    region: Optional[str]= Query(None),
    lat:  Optional[float]= Query(None),
    lon:  Optional[float]= Query(None),
    current_user: User   = Depends(get_current_user),
):
    """5-day forecast from OpenWeatherMap, in the request language."""
    _require_key()
    lang = request_lang(request)
    resolved = _resolve_coords(city, lat, lon, region)

    params = {
        **resolved["params"],
        "appid": WEATHER_API_KEY,
        "units": "metric",
        "lang":  lang,
        "cnt":   40,   # 5 days × 8 slots/day
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{OPENWEATHER_BASE_URL}/forecast", params=params)
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail=f"City not found: {city}")
            r.raise_for_status()
            return {
                "city":     resolved["label"],
                "forecast": _format_forecast(r.json(), resolved["label"], lang),
            }
    except httpx.HTTPError as exc:
        logger.error("[Weather] OpenWeather forecast error: %s", _describe(exc))
        raise HTTPException(status_code=502, detail="The weather service is unavailable.")
