import aiosqlite
from datetime import datetime, timezone

from app.config import DB_PATH


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_candidate_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS memory_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            person_id INTEGER NOT NULL,

            category TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value TEXT NOT NULL,

            confidence REAL NOT NULL DEFAULT 0.5,

            source_platform TEXT,
            source_chat_id TEXT,
            source_message_id INTEGER,
            source_text TEXT,

            status TEXT NOT NULL DEFAULT 'pending',

            created_at TEXT NOT NULL,
            reviewed_at TEXT,

            FOREIGN KEY(person_id)
                REFERENCES people(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_candidates_person
        ON memory_candidates(person_id, status);

        CREATE INDEX IF NOT EXISTS idx_memory_candidates_status
        ON memory_candidates(status);
        """)

        await db.commit()


async def add_candidate(
    person_id,
    category,
    fact_key,
    fact_value,
    confidence=0.5,
    source_platform=None,
    source_chat_id=None,
    source_message_id=None,
    source_text=None
):
    source_chat = (
        str(source_chat_id)
        if source_chat_id is not None
        else None
    )

    async with aiosqlite.connect(DB_PATH) as db:

        # 同一事实只在同一聊天来源内累计证据。
        # 群A的自述不能拿去强化群B的人物画像。
        cur = await db.execute(
            """
            SELECT id
            FROM memory_candidates
            WHERE person_id=?
              AND category=?
              AND fact_key=?
              AND fact_value=?
              AND source_platform IS ?
              AND source_chat_id IS ?
              AND status='pending'
            LIMIT 1
            """,
            (
                person_id,
                category,
                fact_key,
                fact_value,
                source_platform,
                source_chat,
            )
        )

        existing = await cur.fetchone()

        if existing:
            candidate_id = existing[0]

            # 相同事实再次出现时，不创建重复候选。
            # 只累计独立证据次数，并保留更高置信度。
            await db.execute(
                """
                UPDATE memory_candidates
                SET evidence_count = evidence_count + 1,
                    confidence = MAX(confidence, ?)
                WHERE id=?
                  AND status='pending'
                """,
                (
                    confidence,
                    candidate_id
                )
            )

            await db.commit()
            return candidate_id

        cur = await db.execute(
            """
            INSERT INTO memory_candidates (
                person_id,
                category,
                fact_key,
                fact_value,
                confidence,
                source_platform,
                source_chat_id,
                source_message_id,
                source_text,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                person_id,
                category,
                fact_key,
                fact_value,
                confidence,
                source_platform,
                source_chat,
                source_message_id,
                source_text,
                now()
            )
        )

        await db.commit()
        return cur.lastrowid
