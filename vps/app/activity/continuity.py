from __future__ import annotations

import random
from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


def now_utc():
    return datetime.now(timezone.utc)


def _parse(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def init_continuity_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS activity_continuity (
            id INTEGER PRIMARY KEY CHECK(id=1),
            intended_activity TEXT,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'idle',
            started_at TEXT,
            interrupted_at TEXT,
            resumed_at TEXT,
            resume_count INTEGER NOT NULL DEFAULT 0,
            last_reason TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_continuity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            activity TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        );
        """)
        t = now_utc().isoformat()
        await db.execute(
            """
            INSERT OR IGNORE INTO activity_continuity
            (id, status, updated_at)
            VALUES (1, 'idle', ?)
            """,
            (t,),
        )
        await db.commit()


async def _event(db, event_type, activity, reason=None):
    await db.execute(
        """
        INSERT INTO activity_continuity_events
        (event_type, activity, reason, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            event_type,
            activity,
            reason,
            now_utc().isoformat(),
        ),
    )


async def get_continuity_state():
    await init_continuity_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT intended_activity, source, status,
                   started_at, interrupted_at, resumed_at,
                   resume_count, last_reason, updated_at
            FROM activity_continuity
            WHERE id=1
            """
        )
        row = await cur.fetchone()

    return {
        "intended_activity": row[0],
        "source": row[1],
        "status": row[2],
        "started_at": row[3],
        "interrupted_at": row[4],
        "resumed_at": row[5],
        "resume_count": row[6],
        "last_reason": row[7],
        "updated_at": row[8],
    }


async def start_activity_intention(activity, *, source="autonomous", reason=None):
    await init_continuity_db()
    t = now_utc().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE activity_continuity
            SET intended_activity=?,
                source=?,
                status='active',
                started_at=?,
                interrupted_at=NULL,
                resumed_at=NULL,
                resume_count=0,
                last_reason=?,
                updated_at=?
            WHERE id=1
            """,
            (activity, source, t, reason, t),
        )
        await _event(db, "started", activity, reason)
        await db.commit()
    return await get_continuity_state()


async def mark_interrupted(activity, *, reason="conversation"):
    await init_continuity_db()
    current = await get_continuity_state()
    if (
        current.get("status") == "interrupted"
        and current.get("intended_activity") == activity
    ):
        return current

    t = now_utc().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE activity_continuity
            SET intended_activity=?,
                status='interrupted',
                interrupted_at=?,
                last_reason=?,
                updated_at=?
            WHERE id=1
            """,
            (activity, t, reason, t),
        )
        await _event(db, "interrupted", activity, reason)
        await db.commit()
    return await get_continuity_state()


async def resolve_interruption(activity):
    """
    Return:
      none      - no matching interruption
      resume    - continue the same activity
      abandon   - let the activity engine choose something new
    """
    state = await get_continuity_state()
    if (
        state.get("status") != "interrupted"
        or state.get("intended_activity") != activity
    ):
        return {"action": "none", "state": state}

    interrupted_at = _parse(state.get("interrupted_at"))
    if interrupted_at is None:
        age_minutes = 0.0
    else:
        age_minutes = max(
            0.0,
            (now_utc() - interrupted_at).total_seconds() / 60.0,
        )

    # Short conversations usually return to the old thing.
    abandon_chance = 0.08
    if age_minutes >= 20:
        abandon_chance = 0.18
    if age_minutes >= 45:
        abandon_chance = 0.38
    if age_minutes >= 90:
        abandon_chance = 0.62

    # Activities with stronger continuity are less likely to be dropped.
    if activity in {"gaming", "reading", "organizing"}:
        abandon_chance *= 0.75
    elif activity in {"idle", "dazing", "phone"}:
        abandon_chance *= 1.20

    abandon_chance = max(0.03, min(abandon_chance, 0.85))

    t = now_utc().isoformat()
    if random.random() < abandon_chance:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                UPDATE activity_continuity
                SET status='abandoned',
                    last_reason='conversation_changed_momentum',
                    updated_at=?
                WHERE id=1
                """,
                (t,),
            )
            await _event(
                db,
                "abandoned",
                activity,
                "conversation_changed_momentum",
            )
            await db.commit()
        return {
            "action": "abandon",
            "age_minutes": age_minutes,
            "state": await get_continuity_state(),
        }

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE activity_continuity
            SET status='active',
                resumed_at=?,
                resume_count=resume_count+1,
                last_reason='conversation_ended_resume',
                updated_at=?
            WHERE id=1
            """,
            (t, t),
        )
        await _event(
            db,
            "resumed",
            activity,
            "conversation_ended_resume",
        )
        await db.commit()

    return {
        "action": "resume",
        "age_minutes": age_minutes,
        "state": await get_continuity_state(),
    }


async def finish_activity_intention(activity, *, reason="activity_changed"):
    await init_continuity_db()
    state = await get_continuity_state()
    if state.get("intended_activity") != activity:
        return state

    t = now_utc().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE activity_continuity
            SET status='completed',
                last_reason=?,
                updated_at=?
            WHERE id=1
            """,
            (reason, t),
        )
        await _event(db, "completed", activity, reason)
        await db.commit()
    return await get_continuity_state()
