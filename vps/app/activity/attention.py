from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH
from app.activity.needs import get_needs, set_needs


ACTIVE_WINDOW_SECONDS = 12 * 60


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


async def init_attention_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS attention_state (
            id INTEGER PRIMARY KEY CHECK(id=1),
            focus_type TEXT NOT NULL,
            person_id INTEGER,
            chat_id TEXT,
            interrupted_activity TEXT,
            started_at TEXT,
            last_interaction_at TEXT,
            updated_at TEXT NOT NULL
        );
        """)

        t = now_utc().isoformat()
        await db.execute(
            """
            INSERT OR IGNORE INTO attention_state
            (
                id, focus_type, person_id, chat_id,
                interrupted_activity, started_at,
                last_interaction_at, updated_at
            )
            VALUES (1, 'background', NULL, NULL, NULL, NULL, NULL, ?)
            """,
            (t,),
        )
        await db.commit()


async def focus_on_conversation(
    *,
    person_id: int,
    chat_id,
    current_activity: str,
):
    await init_attention_db()
    t = now_utc().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT focus_type, interrupted_activity
            FROM attention_state
            WHERE id=1
            """
        )
        row = await cur.fetchone()

        old_focus = row[0] if row else "background"
        old_interrupted = row[1] if row else None

        interrupted = (
            old_interrupted
            if old_focus == "conversation"
            else current_activity
        )

        await db.execute(
            """
            UPDATE attention_state
            SET focus_type='conversation',
                person_id=?,
                chat_id=?,
                interrupted_activity=?,
                started_at=CASE
                    WHEN focus_type='conversation'
                    THEN started_at
                    ELSE ?
                END,
                last_interaction_at=?,
                updated_at=?
            WHERE id=1
            """,
            (
                int(person_id),
                str(chat_id),
                interrupted,
                t,
                t,
                t,
            ),
        )
        await db.commit()

    # Real conversation lightly satisfies social need and boredom.
    try:
        needs = await get_needs()
        await set_needs(
            social_need=float(needs.get("social_need") or 0.0) - 0.035,
            boredom=float(needs.get("boredom") or 0.0) - 0.018,
        )
    except Exception:
        pass


async def get_attention_state():
    await init_attention_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                focus_type, person_id, chat_id,
                interrupted_activity, started_at,
                last_interaction_at, updated_at
            FROM attention_state
            WHERE id=1
            """
        )
        row = await cur.fetchone()

    if not row:
        return {
            "focus_type": "background",
            "active": False,
        }

    last = _parse(row[5])
    age = None
    active = False

    if row[0] == "conversation" and last:
        age = (now_utc() - last).total_seconds()
        active = 0 <= age <= ACTIVE_WINDOW_SECONDS

    return {
        "focus_type": row[0],
        "person_id": row[1],
        "chat_id": row[2],
        "interrupted_activity": row[3],
        "started_at": row[4],
        "last_interaction_at": row[5],
        "updated_at": row[6],
        "age_seconds": age,
        "active": active,
    }


async def attention_blocks_activity_change():
    state = await get_attention_state()

    if state.get("active"):
        return True

    if state.get("focus_type") == "conversation":
        await release_attention()

    return False


async def release_attention():
    await init_attention_db()
    t = now_utc().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE attention_state
            SET focus_type='background',
                person_id=NULL,
                chat_id=NULL,
                interrupted_activity=NULL,
                started_at=NULL,
                last_interaction_at=NULL,
                updated_at=?
            WHERE id=1
            """,
            (t,),
        )
        await db.commit()


def render_attention_context(state):
    if not state or not state.get("active"):
        return (
            "当前没有被聊天持续占用注意力，"
            "可以继续自己的生活节奏。"
        )

    old = state.get("interrupted_activity") or "原来的事"

    return (
        "当前注意力正在这段聊天上；"
        f"聊天前正在做：{old}。"
        "这只是暂时把注意力转到对话，"
        "不等于原来的生活活动已经结束。"
        "聊天安静一阵后会自然回到自己的节奏。"
    )
