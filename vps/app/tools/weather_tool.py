import asyncio
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


LOCATIONS = {
    "tokyo": {
        "name": "东京",
        "latitude": 35.6762,
        "longitude": 139.6503,
        "timezone": "Asia/Tokyo",
    },
    "zhengzhou": {
        "name": "郑州",
        "latitude": 34.7466,
        "longitude": 113.6254,
        "timezone": "Asia/Shanghai",
    },
}


# 常用城市采用固定坐标，避免地名歧义。
# 例如 Open-Meteo geocoding 曾把“东京”解析成江苏同名地点。
KNOWN_WEATHER_PLACES = {
    "东京": {
        "name": "东京",
        "admin1": "东京都",
        "country": "日本",
        "latitude": 35.6762,
        "longitude": 139.6503,
        "timezone": "Asia/Tokyo",
    },
    "东京市": {
        "name": "东京",
        "admin1": "东京都",
        "country": "日本",
        "latitude": 35.6762,
        "longitude": 139.6503,
        "timezone": "Asia/Tokyo",
    },
    "大阪": {
        "name": "大阪市",
        "admin1": "大阪府",
        "country": "日本",
        "latitude": 34.6937,
        "longitude": 135.5023,
        "timezone": "Asia/Tokyo",
    },
    "大阪市": {
        "name": "大阪市",
        "admin1": "大阪府",
        "country": "日本",
        "latitude": 34.6937,
        "longitude": 135.5023,
        "timezone": "Asia/Tokyo",
    },
    "横滨": {
        "name": "横滨市",
        "admin1": "神奈川县",
        "country": "日本",
        "latitude": 35.4437,
        "longitude": 139.6380,
        "timezone": "Asia/Tokyo",
    },
    "横浜": {
        "name": "横滨市",
        "admin1": "神奈川县",
        "country": "日本",
        "latitude": 35.4437,
        "longitude": 139.6380,
        "timezone": "Asia/Tokyo",
    },
    "京都": {
        "name": "京都市",
        "admin1": "京都府",
        "country": "日本",
        "latitude": 35.0116,
        "longitude": 135.7681,
        "timezone": "Asia/Tokyo",
    },
    "名古屋": {
        "name": "名古屋市",
        "admin1": "爱知县",
        "country": "日本",
        "latitude": 35.1815,
        "longitude": 136.9066,
        "timezone": "Asia/Tokyo",
    },
    "札幌": {
        "name": "札幌市",
        "admin1": "北海道",
        "country": "日本",
        "latitude": 43.0618,
        "longitude": 141.3545,
        "timezone": "Asia/Tokyo",
    },
    "福冈": {
        "name": "福冈市",
        "admin1": "福冈县",
        "country": "日本",
        "latitude": 33.5904,
        "longitude": 130.4017,
        "timezone": "Asia/Tokyo",
    },
    "郑州": {
        "name": "郑州",
        "admin1": "河南",
        "country": "中国",
        "latitude": 34.7466,
        "longitude": 113.6254,
        "timezone": "Asia/Shanghai",
    },
    "北京": {
        "name": "北京",
        "admin1": "北京市",
        "country": "中国",
        "latitude": 39.9042,
        "longitude": 116.4074,
        "timezone": "Asia/Shanghai",
    },
    "上海": {
        "name": "上海",
        "admin1": "上海市",
        "country": "中国",
        "latitude": 31.2304,
        "longitude": 121.4737,
        "timezone": "Asia/Shanghai",
    },
    "广州": {
        "name": "广州",
        "admin1": "广东",
        "country": "中国",
        "latitude": 23.1291,
        "longitude": 113.2644,
        "timezone": "Asia/Shanghai",
    },
    "深圳": {
        "name": "深圳",
        "admin1": "广东",
        "country": "中国",
        "latitude": 22.5431,
        "longitude": 114.0579,
        "timezone": "Asia/Shanghai",
    },
    "香港": {
        "name": "香港",
        "admin1": "香港",
        "country": "中国",
        "latitude": 22.3193,
        "longitude": 114.1694,
        "timezone": "Asia/Hong_Kong",
    },
    "纽约": {
        "name": "纽约市",
        "admin1": "纽约州",
        "country": "美国",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "timezone": "America/New_York",
    },
    "纽约市": {
        "name": "纽约市",
        "admin1": "纽约州",
        "country": "美国",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "timezone": "America/New_York",
    },
    "伦敦": {
        "name": "伦敦",
        "admin1": "英格兰",
        "country": "英国",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "timezone": "Europe/London",
    },
    "巴黎": {
        "name": "巴黎",
        "admin1": "法兰西岛",
        "country": "法国",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "timezone": "Europe/Paris",
    },
    "首尔": {
        "name": "首尔特别市",
        "admin1": "首尔特别市",
        "country": "韩国",
        "latitude": 37.5665,
        "longitude": 126.9780,
        "timezone": "Asia/Seoul",
    },
    "埼玉": {
        "name": "埼玉市",
        "admin1": "埼玉县",
        "country": "日本",
        "latitude": 35.8617,
        "longitude": 139.6455,
        "timezone": "Asia/Tokyo",
    },
    "埼玉市": {
        "name": "埼玉市",
        "admin1": "埼玉县",
        "country": "日本",
        "latitude": 35.8617,
        "longitude": 139.6455,
        "timezone": "Asia/Tokyo",
    },
}


WEATHER_QUERY_ALIASES = {
    # 日本
    "埼玉": "Saitama",
    "埼玉市": "Saitama",
    "川口": "Kawaguchi",
    "川口市": "Kawaguchi",
    "千叶": "Chiba",
    "千叶市": "Chiba",
    "神户": "Kobe",
    "神户市": "Kobe",
    "仙台": "Sendai",
    "仙台市": "Sendai",
    "广岛": "Hiroshima",
    "广岛市": "Hiroshima",
    "那霸": "Naha",
    "冲绳": "Naha",
    # 中国常见城市，避免同名乡镇优先
    "洛阳": "Luoyang",
    "洛阳市": "Luoyang",
    "成都": "Chengdu",
    "重庆": "Chongqing",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "杭州": "Hangzhou",
    "南京": "Nanjing",
    "天津": "Tianjin",
    "苏州": "Suzhou",
    "青岛": "Qingdao",
    "长沙": "Changsha",
    "厦门": "Xiamen",
    "昆明": "Kunming",
    "哈尔滨": "Harbin",
    "沈阳": "Shenyang",
    # 世界主要城市
    "纽约": "New York",
    "纽约市": "New York",
    "伦敦": "London",
    "巴黎": "Paris",
    "首尔": "Seoul",
    "曼谷": "Bangkok",
    "新加坡": "Singapore",
    "悉尼": "Sydney",
    "墨尔本": "Melbourne",
    "洛杉矶": "Los Angeles",
    "旧金山": "San Francisco",
    "华盛顿": "Washington DC",
    "多伦多": "Toronto",
    "温哥华": "Vancouver",
    "柏林": "Berlin",
    "罗马": "Rome",
    "马德里": "Madrid",
    "莫斯科": "Moscow",
    "迪拜": "Dubai",
    "伊斯坦布尔": "Istanbul",
    "吉隆坡": "Kuala Lumpur",
    "胡志明市": "Ho Chi Minh City",
    "河内": "Hanoi",
    "台北": "Taipei",
    "澳门": "Macau",
}


WEATHER_CODES = {
    0: "晴",
    1: "大致晴朗",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    56: "冻毛毛雨",
    57: "较强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "较强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "雷雨伴小冰雹",
    99: "雷雨伴冰雹",
}


def describe_weather(code):
    try:
        return WEATHER_CODES.get(int(code), "天气情况未知")
    except Exception:
        return "天气情况未知"


def _fetch_weather_sync(location_key):
    location = LOCATIONS[location_key]

    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "timezone": location["timezone"],
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
        ]),
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
        ]),
        "forecast_days": 3,
    }

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ying-AI-Companion/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def get_weather(location_key):
    if location_key not in LOCATIONS:
        raise ValueError(f"unknown location: {location_key}")

    raw = await asyncio.to_thread(
        _fetch_weather_sync,
        location_key,
    )

    location = LOCATIONS[location_key]
    current = raw.get("current") or {}
    daily = raw.get("daily") or {}

    daily_codes = daily.get("weather_code") or []
    temp_max = daily.get("temperature_2m_max") or []
    temp_min = daily.get("temperature_2m_min") or []
    rain_prob = daily.get("precipitation_probability_max") or []

    return {
        "location_key": location_key,
        "city": location["name"],
        "timezone": location["timezone"],

        "time": current.get("time"),
        "temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),

        "weather_code": current.get("weather_code"),
        "weather": describe_weather(
            current.get("weather_code")
        ),

        "today_weather": (
            describe_weather(daily_codes[0])
            if len(daily_codes) > 0
            else None
        ),
        "today_max": temp_max[0] if len(temp_max) > 0 else None,
        "today_min": temp_min[0] if len(temp_min) > 0 else None,
        "today_rain_probability": (
            rain_prob[0]
            if len(rain_prob) > 0
            else None
        ),

        "tomorrow_weather": (
            describe_weather(daily_codes[1])
            if len(daily_codes) > 1
            else None
        ),
        "tomorrow_max": temp_max[1] if len(temp_max) > 1 else None,
        "tomorrow_min": temp_min[1] if len(temp_min) > 1 else None,
        "tomorrow_rain_probability": (
            rain_prob[1]
            if len(rain_prob) > 1
            else None
        ),
        "day_after_tomorrow_weather": (
            describe_weather(daily_codes[2]) if len(daily_codes) > 2 else None
        ),
        "day_after_tomorrow_max": temp_max[2] if len(temp_max) > 2 else None,
        "day_after_tomorrow_min": temp_min[2] if len(temp_min) > 2 else None,
        "day_after_tomorrow_rain_probability": rain_prob[2] if len(rain_prob) > 2 else None,
    }


async def get_world_weather():
    results = {}

    for key in ("tokyo", "zhengzhou"):
        location = LOCATIONS[key]
        cache_key = (
            f"{round(location['latitude'], 3)},"
            f"{round(location['longitude'], 3)}"
        )

        cached = await get_cached_weather(cache_key)

        if cached:
            results[key] = cached["weather"]
            continue

        weather = await get_weather(key)

        await save_weather_cache(
            cache_key=cache_key,
            query_name=location["name"],
            resolved_name=location["name"],
            country="日本" if key == "tokyo" else "中国",
            latitude=location["latitude"],
            longitude=location["longitude"],
            timezone_name=location["timezone"],
            weather=weather,
        )

        results[key] = weather

    return results


def _geocode_sync(place_name):
    params = {
        "name": place_name,
        "count": 10,
        "language": "zh",
        "format": "json",
    }

    url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ying-AI-Companion/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def resolve_location(place_name):
    place_name = str(place_name or "").strip()

    if not place_name:
        return None

    raw = await asyncio.to_thread(
        _geocode_sync,
        place_name,
    )

    results = raw.get("results") or []

    if not results:
        return None

    item = results[0]

    return {
        "query": place_name,
        "name": item.get("name"),
        "admin1": item.get("admin1"),
        "country": item.get("country"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "timezone": item.get("timezone") or "auto",
    }


from app.tools.place_aliases import normalize_weather_place

from app.tools.weather_cache import (
    get_cached_weather,
    save_weather_cache,
)


def _fetch_weather_by_coords_sync(
    latitude,
    longitude,
    timezone_name,
):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone_name or "auto",
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
        ]),
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
        ]),
        "forecast_days": 3,
    }

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ying-AI-Companion/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_weather_result(raw):
    current = raw.get("current") or {}
    daily = raw.get("daily") or {}

    daily_codes = daily.get("weather_code") or []
    temp_max = daily.get("temperature_2m_max") or []
    temp_min = daily.get("temperature_2m_min") or []
    rain_prob = daily.get("precipitation_probability_max") or []

    return {
        "time": current.get("time"),
        "temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),

        "weather_code": current.get("weather_code"),
        "weather": describe_weather(
            current.get("weather_code")
        ),

        "today_weather": (
            describe_weather(daily_codes[0])
            if len(daily_codes) > 0
            else None
        ),
        "today_max": (
            temp_max[0]
            if len(temp_max) > 0
            else None
        ),
        "today_min": (
            temp_min[0]
            if len(temp_min) > 0
            else None
        ),
        "today_rain_probability": (
            rain_prob[0]
            if len(rain_prob) > 0
            else None
        ),

        "tomorrow_weather": (
            describe_weather(daily_codes[1])
            if len(daily_codes) > 1
            else None
        ),
        "tomorrow_max": (
            temp_max[1]
            if len(temp_max) > 1
            else None
        ),
        "tomorrow_min": (
            temp_min[1]
            if len(temp_min) > 1
            else None
        ),
        "tomorrow_rain_probability": (
            rain_prob[1]
            if len(rain_prob) > 1
            else None
        ),
        "day_after_tomorrow_weather": (
            describe_weather(daily_codes[2]) if len(daily_codes) > 2 else None
        ),
        "day_after_tomorrow_max": temp_max[2] if len(temp_max) > 2 else None,
        "day_after_tomorrow_min": temp_min[2] if len(temp_min) > 2 else None,
        "day_after_tomorrow_rain_probability": rain_prob[2] if len(rain_prob) > 2 else None,
    }


async def get_weather_for_place(place_name, required_day="today"):
    original_name = str(place_name or "").strip()
    lookup_name = normalize_weather_place(original_name)

    place = await resolve_location(lookup_name)

    if not place:
        return None

    cache_key = (
        f"{round(place['latitude'], 3)},"
        f"{round(place['longitude'], 3)}"
    )

    cached = await get_cached_weather(cache_key)

    if cached and (required_day != "day_after_tomorrow" or
                   cached["weather"].get("day_after_tomorrow_weather") is not None):
        return {
            "place": place,
            "weather": cached["weather"],
            "cached": True,
            "fetched_at": cached["fetched_at"],
            "requested_place": original_name,
            "lookup_place": lookup_name,
        }

    raw = await asyncio.to_thread(
        _fetch_weather_by_coords_sync,
        place["latitude"],
        place["longitude"],
        place["timezone"],
    )

    weather = _normalize_weather_result(raw)

    await save_weather_cache(
        cache_key=cache_key,
        query_name=place_name,
        resolved_name=place["name"],
        country=place["country"],
        latitude=place["latitude"],
        longitude=place["longitude"],
        timezone_name=place["timezone"],
        weather=weather,
    )

    return {
        "place": place,
        "weather": weather,
        "cached": False,
        "fetched_at": None,
        "requested_place": original_name,
        "lookup_place": lookup_name,
    }


def format_weather_reply(result, day="today"):
    """Use only observed/forecast fields returned for the resolved location."""
    place = result.get("place") or {}
    weather = result.get("weather") or {}
    city = str(place.get("name") or result.get("requested_place") or "该地区")
    requested = str(result.get("requested_place") or city)
    lookup = str(result.get("lookup_place") or city)
    region = f"{city}（{place['country']}）" if place.get("country") and city != place.get("country") else city
    def value(key, suffix=""):
        x = weather.get(key)
        return f"{x}{suffix}" if x is not None else None
    def temperatures(low, high):
        a, b = value(low), value(high)
        if a is not None and b is not None:
            return f"{a}～{b}℃"
        return f"最低{a}℃" if a is not None else (f"最高{b}℃" if b is not None else None)
    if day == "day_after_tomorrow":
        parts = [value("day_after_tomorrow_weather"),
                 temperatures("day_after_tomorrow_min", "day_after_tomorrow_max")]
        rain = value("day_after_tomorrow_rain_probability", "%")
        if rain is not None: parts.append(f"最高降雨概率{rain}")
        prefix = f"{region}后天预计："
    elif day == "tomorrow":
        parts = [value("tomorrow_weather"), temperatures("tomorrow_min", "tomorrow_max")]
        rain = value("tomorrow_rain_probability", "%")
        if rain is not None: parts.append(f"最高降雨概率{rain}")
        prefix = f"{region}明天预计："
    else:
        parts = [value("weather"), value("temperature", "℃")]
        feel = value("apparent_temperature", "℃")
        if feel is not None: parts.append(f"体感{feel}")
        overall = value("today_weather")
        if overall is not None: parts.append(f"今日预报{overall}")
        range_text = temperatures("today_min", "today_max")
        if range_text is not None: parts.append(range_text)
        rain = value("today_rain_probability", "%")
        if rain is not None: parts.append(f"最高降雨概率{rain}")
        observed = str(weather.get("time") or "").replace("T", " ")[:16]
        prefix = f"{region}当地时间{observed}：" if observed else f"{region}目前："
    parts = [x for x in parts if x]
    if not parts:
        return f"{city}这次没拿到可用的天气数据，稍后再查。"
    note = f"（按{lookup}区域天气数据）" if requested != lookup else ""
    return prefix + "，".join(parts) + note + "。数据来源：Open-Meteo。"


def _nominatim_geocode_sync(place_name):
    params = {
        "q": place_name,
        "format": "jsonv2",
        "limit": 5,
        "addressdetails": 1,
        "accept-language": "zh-CN,zh,en",
    }

    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ying-AI-Companion/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def resolve_location(place_name):
    place_name = str(place_name or "").strip()

    if not place_name:
        return None

    known = KNOWN_WEATHER_PLACES.get(place_name)
    if known:
        return {
            "query": place_name,
            "lookup_query": place_name,
            **known,
            "source": "fixed-known-place",
        }

    alias = WEATHER_QUERY_ALIASES.get(place_name)

    candidates = []
    if alias:
        candidates.append(alias)

    candidates.append(place_name)

    if (
        len(place_name) <= 8
        and not place_name.endswith(
            ("市", "区", "县", "縣", "州", "府", "省")
        )
    ):
        candidates.append(place_name + "市")

    # 去重但保留顺序。
    candidates = list(dict.fromkeys(candidates))

    all_items = []

    # Open-Meteo 可能返回同名乡镇，因此不能拿第一条就结束。
    # 收集多个候选，再优先首都/行政中心/大城市与高人口结果。
    for candidate in candidates:
        try:
            raw = await asyncio.to_thread(
                _geocode_sync,
                candidate,
            )
            for item in raw.get("results") or []:
                item = dict(item)
                item["_lookup_query"] = candidate
                all_items.append(item)
        except Exception:
            continue

    if all_items:
        def score(item):
            feature = str(item.get("feature_code") or "")
            feature_score = {
                "PPLC": 120.0,
                "PPLA": 100.0,
                "PPLA2": 82.0,
                "PPLA3": 62.0,
                "PPLA4": 48.0,
                "PPL": 25.0,
                "PPLL": 12.0,
            }.get(feature, 0.0)

            try:
                population = float(item.get("population") or 0)
            except Exception:
                population = 0.0

            # 人口只做温和加权，避免小行政中心完全压过知名大城市。
            pop_score = min(55.0, (population / 100000.0) ** 0.5 * 8.0)

            name = str(item.get("name") or "").lower().replace(" ", "")
            lookup = str(item.get("_lookup_query") or "").lower().replace(" ", "")
            original = place_name.lower().replace(" ", "")

            exact_score = 0.0
            if name == lookup:
                exact_score += 35.0
            if name == original:
                exact_score += 30.0

            # 查询别名（例如 Seoul/New York）是人为消歧信号。
            alias_bonus = 18.0 if alias and item.get("_lookup_query") == alias else 0.0

            return feature_score + pop_score + exact_score + alias_bonus

        item = max(all_items, key=score)

        return {
            "query": place_name,
            "lookup_query": item.get("_lookup_query") or place_name,
            "name": item.get("name"),
            "admin1": item.get("admin1"),
            "country": item.get("country"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "timezone": item.get("timezone") or "auto",
            "source": "open-meteo-ranked",
        }

    # OpenStreetMap 作为最后兜底。
    try:
        results = await asyncio.to_thread(
            _nominatim_geocode_sync,
            place_name,
        )

        if not results:
            return None

        item = results[0]
        address = item.get("address") or {}

        resolved_name = (
            address.get("city")
            or address.get("town")
            or address.get("county")
            or address.get("municipality")
            or address.get("village")
            or item.get("name")
            or place_name
        )

        admin1 = (
            address.get("state")
            or address.get("province")
            or address.get("region")
        )

        return {
            "query": place_name,
            "lookup_query": place_name,
            "name": resolved_name,
            "admin1": admin1,
            "country": address.get("country"),
            "latitude": float(item["lat"]),
            "longitude": float(item["lon"]),
            "timezone": "auto",
            "source": "openstreetmap",
        }

    except Exception:
        return None


async def refresh_fixed_weather_cache():
    """
    强制刷新东京 + 郑州固定天气。
    不读取旧缓存，专门给 VPS 定时任务使用。
    """
    results = {}

    for key in ("tokyo", "zhengzhou"):
        location = LOCATIONS[key]

        # 直接请求最新天气，不走普通3小时缓存
        weather = await get_weather(key)

        cache_key = (
            f"{round(location['latitude'], 3)},"
            f"{round(location['longitude'], 3)}"
        )

        await save_weather_cache(
            cache_key=cache_key,
            query_name=location["name"],
            resolved_name=location["name"],
            country="日本" if key == "tokyo" else "中国",
            latitude=location["latitude"],
            longitude=location["longitude"],
            timezone_name=location["timezone"],
            weather=weather,
        )

        results[key] = weather

    return results


def _fetch_location_weather_sync(location):
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "timezone": location.get("timezone") or "auto",
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
        ]),
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
        ]),
        "forecast_days": 3,
    }

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ying-AI-Companion/1.0",
        },
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def get_city_weather(place_name):
    """
    查询任意城市/地区的实时天气 + 今天/明天预报。
    不影响东京/郑州固定生活天气系统。
    """
    location = await resolve_location(place_name)

    if not location:
        return None

    raw = await asyncio.to_thread(
        _fetch_location_weather_sync,
        location,
    )

    current = raw.get("current") or {}
    daily = raw.get("daily") or {}

    daily_codes = daily.get("weather_code") or []
    temp_max = daily.get("temperature_2m_max") or []
    temp_min = daily.get("temperature_2m_min") or []
    rain_prob = daily.get("precipitation_probability_max") or []

    return {
        "query": place_name,
        "city": location.get("name"),
        "admin1": location.get("admin1"),
        "country": location.get("country"),
        "timezone": location.get("timezone"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),

        "time": current.get("time"),
        "temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),

        "weather_code": current.get("weather_code"),
        "weather": describe_weather(
            current.get("weather_code")
        ),

        "today_weather": (
            describe_weather(daily_codes[0])
            if len(daily_codes) > 0
            else None
        ),
        "today_max": (
            temp_max[0] if len(temp_max) > 0 else None
        ),
        "today_min": (
            temp_min[0] if len(temp_min) > 0 else None
        ),
        "today_rain_probability": (
            rain_prob[0] if len(rain_prob) > 0 else None
        ),

        "tomorrow_weather": (
            describe_weather(daily_codes[1])
            if len(daily_codes) > 1
            else None
        ),
        "tomorrow_max": (
            temp_max[1] if len(temp_max) > 1 else None
        ),
        "tomorrow_min": (
            temp_min[1] if len(temp_min) > 1 else None
        ),
        "tomorrow_rain_probability": (
            rain_prob[1] if len(rain_prob) > 1 else None
        ),
        "day_after_tomorrow_weather": (
            describe_weather(daily_codes[2]) if len(daily_codes) > 2 else None
        ),
        "day_after_tomorrow_max": temp_max[2] if len(temp_max) > 2 else None,
        "day_after_tomorrow_min": temp_min[2] if len(temp_min) > 2 else None,
        "day_after_tomorrow_rain_probability": rain_prob[2] if len(rain_prob) > 2 else None,
    }
