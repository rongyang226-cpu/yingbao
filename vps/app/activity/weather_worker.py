import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH, TELEGRAM_OWNER_ID
from app.tools.weather_tool import get_world_weather

log = logging.getLogger(__name__)

OWNER_TZ = ZoneInfo("Asia/Shanghai")
SEND_HOUR = 8
SEND_MINUTE = 0


def next_weather_time(now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    local_now = now_utc.astimezone(OWNER_TZ)

    target = local_now.replace(
        hour=SEND_HOUR,
        minute=SEND_MINUTE,
        second=0,
        microsecond=0,
    )

    if target <= local_now:
        target += timedelta(days=1)

    return target.astimezone(timezone.utc)


async def init_weather_schedule():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_weather_schedule (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                next_run_at TEXT NOT NULL,
                last_sent_date TEXT,
                status TEXT NOT NULL DEFAULT 'ready',
                updated_at TEXT NOT NULL
            )
            """
        )

        now_utc = datetime.now(timezone.utc)
        next_run = next_weather_time(now_utc)

        await db.execute(
            """
            INSERT OR IGNORE INTO daily_weather_schedule (
                id,
                next_run_at,
                updated_at
            )
            VALUES (1, ?, ?)
            """,
            (
                next_run.isoformat(),
                now_utc.isoformat(),
            )
        )

        await db.commit()


async def get_schedule():
    await init_weather_schedule()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT next_run_at, status
            FROM daily_weather_schedule
            WHERE id=1
            """
        )
        row = await cur.fetchone()

    return {
        "next_run_at": row[0],
        "status": row[1],
    }


async def complete_schedule():
    now_utc = datetime.now(timezone.utc)
    local_now = now_utc.astimezone(OWNER_TZ)

    next_run = (
        local_now + timedelta(days=1)
    ).replace(
        hour=SEND_HOUR,
        minute=SEND_MINUTE,
        second=0,
        microsecond=0,
    ).astimezone(timezone.utc)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE daily_weather_schedule
            SET next_run_at=?,
                last_sent_date=?,
                status='ready',
                updated_at=?
            WHERE id=1
            """,
            (
                next_run.isoformat(),
                local_now.date().isoformat(),
                now_utc.isoformat(),
            )
        )
        await db.commit()


def build_weather_message(weather):
    zz = weather["zhengzhou"]
    tk = weather["tokyo"]

    text = f"早。郑州现在{zz['weather']}，{zz['temperature']}℃。"

    rain = zz.get("today_rain_probability")
    if rain is not None:
        if rain >= 50:
            text += f"今天最高降雨概率{rain}%，出门带伞。"
        else:
            text += "今天下雨可能不大。"

    text += f"东京这边现在{tk['weather']}，{tk['temperature']}℃。"

    return text


async def weather_tick(context):
    schedule = await get_schedule()

    due = datetime.fromisoformat(
        schedule["next_run_at"]
    )

    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)

    if now_utc < due:
        return

    if schedule["status"] != "ready":
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE daily_weather_schedule
            SET status='sending',
                updated_at=?
            WHERE id=1
              AND status='ready'
            """,
            (now_utc.isoformat(),)
        )
        await db.commit()

        if cur.rowcount != 1:
            return

    try:
        weather = await get_world_weather()

        await context.bot.send_message(
            chat_id=TELEGRAM_OWNER_ID,
            text=build_weather_message(weather),
        )

        await complete_schedule()

        log.info("Daily weather delivered")

    except Exception:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                UPDATE daily_weather_schedule
                SET status='ready',
                    updated_at=?
                WHERE id=1
                """,
                (datetime.now(timezone.utc).isoformat(),)
            )
            await db.commit()

        log.exception("Daily weather delivery failed")
