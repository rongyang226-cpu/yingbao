import aiosqlite
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import DB_PATH
from app.social.state import now


async def init_life_state_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS life_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),

                energy REAL NOT NULL DEFAULT 0.75,
                social_desire REAL NOT NULL DEFAULT 0.50,

                activity TEXT NOT NULL DEFAULT 'idle',
                sleep_state TEXT NOT NULL DEFAULT 'awake',

                last_wake_at TEXT,
                last_sleep_at TEXT,
                last_proactive_at TEXT,

                updated_at TEXT NOT NULL
            )
            """
        )

        # 兼容旧数据库：自动补齐 Life State 新字段
        cur = await db.execute("PRAGMA table_info(life_state)")
        columns = {row[1] for row in await cur.fetchall()}

        if "restless_reason" not in columns:
            await db.execute(
                "ALTER TABLE life_state ADD COLUMN restless_reason TEXT"
            )

        if "distress" not in columns:
            await db.execute(
                "ALTER TABLE life_state ADD COLUMN distress REAL NOT NULL DEFAULT 0.0"
            )

        if "sleep_attempt_at" not in columns:
            await db.execute(
                "ALTER TABLE life_state ADD COLUMN sleep_attempt_at TEXT"
            )

        if "activity_started_at" not in columns:
            await db.execute(
                "ALTER TABLE life_state ADD COLUMN activity_started_at TEXT"
            )

        await db.execute(
            """
            INSERT OR IGNORE INTO life_state (
                id,
                updated_at
            )
            VALUES (1, ?)
            """,
            (now(),)
        )

        await db.commit()


async def get_life_state():
    await init_life_state_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                energy,
                social_desire,
                activity,
                sleep_state,
                last_wake_at,
                last_sleep_at,
                last_proactive_at,
                restless_reason,
                distress,
                sleep_attempt_at,
                activity_started_at,
                updated_at
            FROM life_state
            WHERE id=1
            """
        )
        row = await cur.fetchone()

    return {
        "energy": row[0],
        "social_desire": row[1],
        "activity": row[2],
        "sleep_state": row[3],
        "last_wake_at": row[4],
        "last_sleep_at": row[5],
        "last_proactive_at": row[6],
        "restless_reason": row[7],
        "distress": row[8],
        "sleep_attempt_at": row[9],
        "activity_started_at": row[10],
        "updated_at": row[11],
    }

def clamp_unit(value):
    return max(0.0, min(1.0, float(value)))


_UNCHANGED = object()


async def update_life_state(
    *,
    energy=None,
    social_desire=None,
    activity=None,
    sleep_state=None,
    last_wake_at=_UNCHANGED,
    last_sleep_at=_UNCHANGED,
    last_proactive_at=_UNCHANGED,
    restless_reason=_UNCHANGED,
    distress=None,
    sleep_attempt_at=_UNCHANGED,
    activity_started_at=_UNCHANGED,
):
    current = await get_life_state()

    new_energy = (
        current["energy"]
        if energy is None
        else clamp_unit(energy)
    )

    new_social = (
        current["social_desire"]
        if social_desire is None
        else clamp_unit(social_desire)
    )

    new_distress = (
        current["distress"]
        if distress is None
        else clamp_unit(distress)
    )

    new_activity = (
        current["activity"]
        if activity is None
        else activity
    )

    def keep_or(value, key):
        if value is _UNCHANGED:
            return current[key]
        return value

    if activity_started_at is _UNCHANGED:
        if activity is not None and activity != current["activity"]:
            new_activity_started_at = now()
        else:
            new_activity_started_at = current["activity_started_at"]
    else:
        new_activity_started_at = activity_started_at

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE life_state
            SET energy=?,
                social_desire=?,
                activity=?,
                sleep_state=?,
                last_wake_at=?,
                last_sleep_at=?,
                last_proactive_at=?,
                restless_reason=?,
                distress=?,
                sleep_attempt_at=?,
                activity_started_at=?,
                updated_at=?
            WHERE id=1
            """,
            (
                new_energy,
                new_social,
                new_activity,
                sleep_state if sleep_state is not None else current["sleep_state"],
                keep_or(last_wake_at, "last_wake_at"),
                keep_or(last_sleep_at, "last_sleep_at"),
                keep_or(last_proactive_at, "last_proactive_at"),
                keep_or(restless_reason, "restless_reason"),
                new_distress,
                keep_or(sleep_attempt_at, "sleep_attempt_at"),
                new_activity_started_at,
                now(),
            )
        )
        await db.commit()

    return await get_life_state()


async def init_daily_cycle_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_cycle (
                local_date TEXT PRIMARY KEY,

                wake_target TEXT NOT NULL,
                sleep_target TEXT NOT NULL,

                energy_baseline REAL NOT NULL,
                social_baseline REAL NOT NULL,

                sleep_difficulty REAL NOT NULL DEFAULT 0.0,

                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


async def get_or_create_daily_cycle(local_date=None):
    await init_daily_cycle_db()

    tz = ZoneInfo("Asia/Tokyo")
    now_local = datetime.now(tz)

    if local_date is None:
        local_date = now_local.date().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                wake_target,
                sleep_target,
                energy_baseline,
                social_baseline,
                sleep_difficulty
            FROM daily_cycle
            WHERE local_date=?
            """,
            (local_date,)
        )
        row = await cur.fetchone()

        if row:
            return {
                "local_date": local_date,
                "wake_target": row[0],
                "sleep_target": row[1],
                "energy_baseline": row[2],
                "social_baseline": row[3],
                "sleep_difficulty": row[4],
            }

        base_date = datetime.fromisoformat(local_date)

        wake_minutes = random.randint(
            7 * 60 + 30,
            9 * 60 + 10,
        )

        sleep_minutes = random.randint(
            23 * 60 + 20,
            24 * 60 + 50,
        )

        wake_dt = base_date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(minutes=wake_minutes)

        sleep_base = base_date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        sleep_dt = sleep_base + timedelta(
            minutes=sleep_minutes
        )

        energy_baseline = round(
            random.uniform(0.58, 0.82),
            3,
        )

        social_baseline = round(
            random.uniform(0.35, 0.68),
            3,
        )

        sleep_difficulty = round(
            random.uniform(0.08, 0.38),
            3,
        )

        wake_dt = wake_dt.replace(tzinfo=tz)
        sleep_dt = sleep_dt.replace(tzinfo=tz)

        wake_target = wake_dt.isoformat()
        sleep_target = sleep_dt.isoformat()

        await db.execute(
            """
            INSERT INTO daily_cycle (
                local_date,
                wake_target,
                sleep_target,
                energy_baseline,
                social_baseline,
                sleep_difficulty,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                local_date,
                wake_target,
                sleep_target,
                energy_baseline,
                social_baseline,
                sleep_difficulty,
                now(),
            )
        )

        await db.commit()

    return {
        "local_date": local_date,
        "wake_target": wake_target,
        "sleep_target": sleep_target,
        "energy_baseline": energy_baseline,
        "social_baseline": social_baseline,
        "sleep_difficulty": sleep_difficulty,
    }


def get_daily_phase(cycle, current_time=None):
    tz = ZoneInfo("Asia/Tokyo")

    if current_time is None:
        current_time = datetime.now(tz)

    wake_at = datetime.fromisoformat(
        cycle["wake_target"]
    )
    sleep_at = datetime.fromisoformat(
        cycle["sleep_target"]
    )

    if current_time < wake_at:
        return "sleeping"

    sleepy_start = sleep_at - timedelta(
        minutes=75
    )

    bedtime_start = sleep_at - timedelta(
        minutes=25
    )

    if current_time < sleepy_start:
        return "active"

    if current_time < bedtime_start:
        return "evening"

    if current_time < sleep_at:
        return "sleepy"

    return "sleep_window"


def evolve_life_values(
    *,
    energy,
    social_desire,
    phase,
    sleep_state="awake",
    energy_baseline=0.70,
    social_baseline,
):
    energy = clamp_unit(energy)
    social_desire = clamp_unit(social_desire)

    if sleep_state == "sleeping":
        energy += 0.0040

    elif phase == "sleeping":
        energy -= 0.0004

    elif phase == "active":
        energy -= 0.0015

    elif phase == "evening":
        energy -= 0.0020

    elif phase == "sleepy":
        energy -= 0.0025

    elif phase == "sleep_window":
        energy -= 0.0015

    # 每5分钟只做非常轻微的基线回归
    energy += (energy_baseline - energy) * 0.002
    social_desire += (
        social_baseline - social_desire
    ) * 0.004

    return {
        "energy": clamp_unit(energy),
        "social_desire": clamp_unit(
            social_desire
        ),
    }


async def record_activity_history(
    activity,
    *,
    started_at=None,
    ended_at=None,
    game_name=None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur = await db.execute(
            "PRAGMA table_info(activity_history)"
        )
        columns = {row[1] for row in await cur.fetchall()}

        if "game_name" not in columns:
            await db.execute(
                "ALTER TABLE activity_history ADD COLUMN game_name TEXT"
            )

        await db.execute(
            """
            INSERT INTO activity_history (
                activity,
                started_at,
                ended_at,
                game_name,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                activity,
                started_at,
                ended_at,
                game_name,
                now(),
            )
        )

        await db.commit()


async def get_recent_activity_history(limit=8):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur = await db.execute(
            """
            SELECT
                activity,
                started_at,
                ended_at,
                game_name,
                created_at
            FROM activity_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),)
        )

        rows = await cur.fetchall()

    return [
        {
            "activity": row[0],
            "started_at": row[1],
            "ended_at": row[2],
            "game_name": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]
