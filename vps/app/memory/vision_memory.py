from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_vision_memory_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS vision_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            source_message_id INTEGER,
            kind TEXT NOT NULL,
            user_caption TEXT,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(platform, chat_id, source_message_id)
        );

        CREATE INDEX IF NOT EXISTS idx_vision_memories_scope
        ON vision_memories(person_id, platform, chat_id, created_at);
        """)
        await db.commit()


async def add_vision_memory(
    *,
    person_id: int,
    platform: str,
    chat_id,
    source_message_id,
    kind: str,
    user_caption: str,
    summary: str,
):
    summary = str(summary or "").strip()
    if not summary:
        return False

    await init_vision_memory_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO vision_memories (
                person_id, platform, chat_id,
                source_message_id, kind, user_caption,
                summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(person_id),
                str(platform),
                str(chat_id),
                source_message_id,
                str(kind),
                str(user_caption or "")[:1000],
                summary[:1800],
                now(),
            ),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_recent_vision_context(
    *,
    person_id: int,
    platform: str,
    chat_id,
    limit: int = 3,
):
    await init_vision_memory_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT kind, user_caption, summary
            FROM vision_memories
            WHERE person_id=?
              AND platform=?
              AND chat_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                int(person_id),
                str(platform),
                str(chat_id),
                int(limit),
            ),
        )
        rows = await cur.fetchall()

    if not rows:
        return "（最近没有可靠的图片内容摘要）"

    lines = []
    for kind, caption, summary in reversed(rows):
        prefix = f"{kind}"
        if caption:
            prefix += f"（对方当时说：{caption[:120]}）"
        lines.append(f"- {prefix}：{summary[:500]}")

    return "\n".join(lines)
