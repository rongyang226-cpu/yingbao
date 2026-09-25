from __future__ import annotations

import re
from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH
from app.social.state_engine import apply_emotion_event
from app.social.bond_engine import apply_bond_event


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_interaction_event_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS interaction_event_receipts (
            platform TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            source_message_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(platform, chat_id, source_message_id, event_type)
        );
        """)
        await db.commit()


def _contains_any(text: str, markers) -> bool:
    t = str(text or "").strip()
    return any(m in t for m in markers)


def classify_interaction_signals(text: str):
    """
    只识别很明确的互动，不做泛化情绪猜测。
    目的是让情绪/关系有真实事件来源，又尽量减少误判。
    """
    t = str(text or "").strip()
    if not t:
        return []

    signals = []

    if _contains_any(t, (
        "别难过", "别伤心", "没事的", "没事啦",
        "我陪你", "有我在", "抱抱", "摸摸",
        "别怕", "不用怕", "慢慢来",
    )):
        signals.append("comfort_received")

    if _contains_any(t, (
        "约好了", "说好了", "答应你", "我答应",
        "第一次一起", "第一次和你", "纪念一下",
        "这是我们的", "我们约定",
    )):
        signals.append("shared_important_moment")

    if _contains_any(t, (
        "你必须", "你给我闭嘴", "滚", "废物",
        "垃圾", "烦死了你", "我命令你",
    )):
        signals.append("argument_pressure")

    # 去重并保留顺序。
    return list(dict.fromkeys(signals))
async def _claim_signal(
    *,
    platform: str,
    chat_id,
    source_message_id,
    event_type: str,
    person_id: int,
):
    await init_interaction_event_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO interaction_event_receipts (
                platform, chat_id, source_message_id,
                event_type, person_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(platform),
                str(chat_id),
                int(source_message_id),
                str(event_type),
                int(person_id),
                now(),
            ),
        )
        await db.commit()
        return cur.rowcount > 0


async def apply_interaction_signals(
    *,
    person_id: int,
    role: str,
    platform: str,
    chat_id,
    source_message_id,
    text: str,
):
    signals = classify_interaction_signals(text)
    if not signals:
        return []

    applied = []

    for event_type in signals:
        claimed = await _claim_signal(
            platform=platform,
            chat_id=chat_id,
            source_message_id=source_message_id,
            event_type=event_type,
            person_id=person_id,
        )
        if not claimed:
            continue

        # 情绪可以针对任何稳定人物产生；
        # bond 只会由 bond_engine 再次确认 OWNER。
        await apply_emotion_event(
            person_id=person_id,
            event_type=event_type,
            reason=f"interaction:{event_type}",
        )

        if role == "OWNER" and event_type in (
            "comfort_received",
            "shared_important_moment",
        ):
            await apply_bond_event(
                person_id=person_id,
                event_type=event_type,
                source_platform=platform,
                source_chat_id=chat_id,
                source_message_id=source_message_id,
            )

        applied.append(event_type)

    return applied
