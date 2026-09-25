"""Weather proxy for the authenticated mobile viewer."""
from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_cache: dict[str, tuple[float, dict]] = {}

def _get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "Yingbao/2.4"})
    with urlopen(req, timeout=8) as response:
        return json.load(response)

async def search_city(query: str) -> dict:
    query = query.strip()[:80]
    if len(query) < 2:
        return {"results": []}
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({
        "name": query, "count": 6, "language": "zh", "format": "json"
    })
    data = await asyncio.to_thread(_get, url)
    return {"results": [{
        "name": x.get("name"), "region": x.get("admin1"),
        "country": x.get("country"), "latitude": x.get("latitude"),
        "longitude": x.get("longitude"), "timezone": x.get("timezone"),
    } for x in data.get("results", [])]}
async def current_weather(lat: float, lon: float, zone: str) -> dict:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("invalid coordinates")
    if not zone or len(zone) > 64 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_/-+" for c in zone):
        raise ValueError("invalid timezone")
    key = f"{lat:.3f},{lon:.3f},{zone}"
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < 600:
        return cached[1]
    url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weather_code,is_day",
        "timezone": zone,
    })
    data = await asyncio.to_thread(_get, url)
    current = data.get("current") or {}
    result = {
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "weather_code": current.get("weather_code"),
        "is_day": current.get("is_day"),
        "observed_at": current.get("time"),
        "timezone": data.get("timezone"),
    }
    _cache[key] = (time.monotonic(), result)
    return result
