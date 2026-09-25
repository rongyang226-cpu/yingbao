from __future__ import annotations

import random
from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH
from app.activity.interests import weighted_choice

TOKYO_TZ = ZoneInfo("Asia/Tokyo")

PLAN_LIBRARY = {
    "morning": [
        ("reading", "上午想安静看点东西"),
        ("organizing", "上午想把房间稍微整理一下"),
        ("walking", "天气合适的话上午出去走走"),
        ("coffee", "上午想去附近坐一会儿"),
    ],
    "afternoon": [
        ("gaming", "下午想认真玩一会儿游戏"),
        ("reading", "下午想继续看点东西"),
        ("walking", "下午天气舒服就出去散步"),
        ("shopping", "下午想顺路补点日用品"),
        ("coffee", "下午想换个地方坐坐"),
    ],
    "evening": [
        ("gaming", "晚上想玩一阵游戏"),
        ("listening", "晚上想安静听点东西"),
        ("reading", "晚上想随便看一会儿"),
        ("resting", "晚上想早点歇下来"),
    ],
}

SLOT_WINDOWS = {
    "morning": (8, 12),
    "afternoon": (13, 18),
    "evening": (18, 22),
}


def now_tokyo():
    return datetime.now(TOKYO_TZ)


async def init_plan_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS daily_intentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_date TEXT NOT NULL,
            slot TEXT NOT NULL,
            activity TEXT NOT NULL,
            note TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            skipped_reason TEXT,
            UNIQUE(local_date, slot)
        );

        CREATE INDEX IF NOT EXISTS idx_daily_intentions_date
        ON daily_intentions(local_date, status);
        """)

        cur = await db.execute(
            "PRAGMA table_info(daily_intentions)"
        )
        cols = {
            row[1]
            for row in await cur.fetchall()
        }

        if "revision_count" not in cols:
            await db.execute(
                "ALTER TABLE daily_intentions "
                "ADD COLUMN revision_count INTEGER NOT NULL DEFAULT 0"
            )

        if "revision_reason" not in cols:
            await db.execute(
                "ALTER TABLE daily_intentions "
                "ADD COLUMN revision_reason TEXT"
            )

        await db.commit()


def _weather_blocks_outdoor(weather):
    if not weather:
        return False

    condition = str(weather.get("weather") or "")

    try:
        rain = float(
            weather.get("today_rain_probability")
            if weather.get("today_rain_probability") is not None
            else 0
        )
    except Exception:
        rain = 0

    try:
        precipitation = float(weather.get("precipitation") or 0)
    except Exception:
        precipitation = 0

    return (
        "雨" in condition
        or "雪" in condition
        or rain >= 65
        or precipitation >= 1.5
    )


async def _pick_for_slot(slot, weather=None):
    options = list(PLAN_LIBRARY[slot])

    if _weather_blocks_outdoor(weather):
        options = [
            item
            for item in options
            if item[0] not in {"walking", "coffee", "shopping"}
        ]

    if not options:
        options = [("resting", "今天就安静待着")]

    activities = [item[0] for item in options]
    chosen = await weighted_choice(
        "activity",
        activities,
    )

    for item in options:
        if item[0] == chosen:
            return item

    return random.choice(options)


async def ensure_today_plan(weather=None):
    await init_plan_db()

    now = now_tokyo()
    local_date = now.date().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT slot
            FROM daily_intentions
            WHERE local_date=?
            """,
            (local_date,),
        )
        existing = {
            row[0]
            for row in await cur.fetchall()
        }

        for slot in ("morning", "afternoon", "evening"):
            if slot in existing:
                continue

            activity, note = await _pick_for_slot(
                slot,
                weather=weather,
            )

            await db.execute(
                """
                INSERT OR IGNORE INTO daily_intentions
                (local_date, slot, activity, note, status, created_at)
                VALUES (?, ?, ?, ?, 'planned', ?)
                """,
                (
                    local_date,
                    slot,
                    activity,
                    note,
                    now.isoformat(),
                ),
            )

        await db.commit()

    return await get_today_plan()


async def reconsider_today_plan(weather=None):
    """
    天气变化会让还没执行的外出计划自然改变主意。
    已完成的计划绝不改写历史。
    """
    await init_plan_db()

    if not _weather_blocks_outdoor(weather):
        return 0

    now = now_tokyo()
    local_date = now.date().isoformat()
    current = current_slot(now.hour)

    outdoor = {"walking", "coffee", "shopping"}
    alternatives = {
        "morning": [
            ("reading", "外面天气不太适合，上午改成在家看点东西"),
            ("organizing", "天气不太适合出门，上午改成整理一下房间"),
        ],
        "afternoon": [
            ("gaming", "外面天气不太适合，下午改成在家玩一会儿"),
            ("reading", "天气不太适合出门，下午改成安静看点东西"),
        ],
        "evening": [
            ("listening", "外面天气不太适合，晚上改成在家听点东西"),
            ("resting", "天气不太适合出门，晚上就早点歇着"),
        ],
    }

    changed = 0

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, slot, activity
            FROM daily_intentions
            WHERE local_date=?
              AND status='planned'
            """,
            (local_date,),
        )
        rows = await cur.fetchall()

        for pid, slot, activity in rows:
            if activity not in outdoor:
                continue

            # 已经过期的时间段交给 expire_old_slots 处理。
            if current is None:
                continue

            options = alternatives.get(
                slot,
                [("resting", "天气不太适合出门，改成在家待着")],
            )
            chosen = await weighted_choice(
                "activity",
                [item[0] for item in options],
            )
            new_activity, note = next(
                item
                for item in options
                if item[0] == chosen
            )

            await db.execute(
                """
                UPDATE daily_intentions
                SET activity=?,
                    note=?,
                    revision_count=revision_count+1,
                    revision_reason='weather_changed'
                WHERE id=?
                  AND status='planned'
                """,
                (
                    new_activity,
                    note,
                    pid,
                ),
            )
            changed += 1

        await db.commit()

    return changed


async def get_today_plan():
    await init_plan_db()
    local_date = now_tokyo().date().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, slot, activity, note, status,
                   created_at, completed_at, skipped_reason,
                   revision_count, revision_reason
            FROM daily_intentions
            WHERE local_date=?
            ORDER BY
              CASE slot
                WHEN 'morning' THEN 1
                WHEN 'afternoon' THEN 2
                WHEN 'evening' THEN 3
                ELSE 4
              END
            """,
            (local_date,),
        )
        rows = await cur.fetchall()

    return [
        {
            "id": row[0],
            "slot": row[1],
            "activity": row[2],
            "note": row[3],
            "status": row[4],
            "created_at": row[5],
            "completed_at": row[6],
            "skipped_reason": row[7],
            "revision_count": row[8],
            "revision_reason": row[9],
        }
        for row in rows
    ]


def current_slot(hour=None):
    hour = now_tokyo().hour if hour is None else int(hour)

    for slot, (start, end) in SLOT_WINDOWS.items():
        if start <= hour < end:
            return slot

    return None


async def get_current_intention():
    slot = current_slot()

    if not slot:
        return None

    local_date = now_tokyo().date().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, slot, activity, note, status
            FROM daily_intentions
            WHERE local_date=?
              AND slot=?
            LIMIT 1
            """,
            (local_date, slot),
        )
        row = await cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "slot": row[1],
        "activity": row[2],
        "note": row[3],
        "status": row[4],
    }


async def complete_matching_intention(activity):
    slot = current_slot()
    if not slot:
        return False

    local_date = now_tokyo().date().isoformat()
    t = now_tokyo().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE daily_intentions
            SET status='completed',
                completed_at=?
            WHERE local_date=?
              AND slot=?
              AND activity=?
              AND status='planned'
            """,
            (t, local_date, slot, activity),
        )
        await db.commit()
        return cur.rowcount > 0


async def expire_old_slots():
    now = now_tokyo()
    local_date = now.date().isoformat()
    hour = now.hour

    expired_slots = []
    for slot, (_start, end) in SLOT_WINDOWS.items():
        if hour >= end:
            expired_slots.append(slot)

    if not expired_slots:
        return 0

    placeholders = ",".join("?" for _ in expired_slots)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            f"""
            UPDATE daily_intentions
            SET status='skipped',
                skipped_reason='time_window_passed'
            WHERE local_date=?
              AND slot IN ({placeholders})
              AND status='planned'
            """,
            (local_date, *expired_slots),
        )
        await db.commit()
        return cur.rowcount


def render_plan(plan):
    if not plan:
        return "今天还没有形成明确的小计划。"

    slot_name = {
        "morning": "上午",
        "afternoon": "下午",
        "evening": "晚上",
    }

    status_name = {
        "planned": "还想做",
        "completed": "已经做了",
        "skipped": "后来没做",
    }

    lines = []
    for item in plan:
        suffix = status_name.get(
            item["status"],
            item["status"],
        )

        if (
            item.get("revision_count", 0) > 0
            and item.get("revision_reason") == "weather_changed"
            and item["status"] == "planned"
        ):
            suffix += "，因为天气改过主意"

        lines.append(
            f"- {slot_name.get(item['slot'], item['slot'])}："
            f"{item['note']}（{suffix}）"
        )

    return "\n".join(lines)
