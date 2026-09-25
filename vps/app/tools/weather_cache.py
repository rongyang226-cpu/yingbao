import aiosqlite
from datetime import datetime, timezone

from app.config import DB_PATH


async def init_weather_cache_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_cache (
                cache_key TEXT PRIMARY KEY,

                query_name TEXT NOT NULL,
                resolved_name TEXT,
                country TEXT,

                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                timezone TEXT,

                weather_json TEXT NOT NULL,

                fetched_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )

        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_cache_expires
            ON weather_cache(expires_at)
            """
        )

        await db.commit()


def utc_now():
    return datetime.now(timezone.utc)


import json
from datetime import timedelta


CACHE_HOURS = 3


async def get_cached_weather(cache_key):
    await init_weather_cache_db()

    now = utc_now()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                query_name,
                resolved_name,
                country,
                latitude,
                longitude,
                timezone,
                weather_json,
                fetched_at,
                expires_at
            FROM weather_cache
            WHERE cache_key=?
              AND expires_at > ?
            """,
            (
                cache_key,
                now.isoformat(),
            )
        )

        row = await cur.fetchone()

    if not row:
        return None

    return {
        "query_name": row[0],
        "resolved_name": row[1],
        "country": row[2],
        "latitude": row[3],
        "longitude": row[4],
        "timezone": row[5],
        "weather": json.loads(row[6]),
        "fetched_at": row[7],
        "expires_at": row[8],
        "cached": True,
    }


async def save_weather_cache(
    *,
    cache_key,
    query_name,
    resolved_name,
    country,
    latitude,
    longitude,
    timezone_name,
    weather,
):
    await init_weather_cache_db()

    fetched_at = utc_now()
    expires_at = fetched_at + timedelta(hours=CACHE_HOURS)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO weather_cache (
                cache_key,
                query_name,
                resolved_name,
                country,
                latitude,
                longitude,
                timezone,
                weather_json,
                fetched_at,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(cache_key) DO UPDATE SET
                query_name=excluded.query_name,
                resolved_name=excluded.resolved_name,
                country=excluded.country,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                timezone=excluded.timezone,
                weather_json=excluded.weather_json,
                fetched_at=excluded.fetched_at,
                expires_at=excluded.expires_at
            """,
            (
                cache_key,
                query_name,
                resolved_name,
                country,
                latitude,
                longitude,
                timezone_name,
                json.dumps(
                    weather,
                    ensure_ascii=False,
                ),
                fetched_at.isoformat(),
                expires_at.isoformat(),
            )
        )

        await db.commit()
