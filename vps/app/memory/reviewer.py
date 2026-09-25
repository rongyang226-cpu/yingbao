import aiosqlite
from datetime import datetime, timezone

from app.config import DB_PATH
from app.social.profiles import add_fact


def now():
    return datetime.now(timezone.utc).isoformat()


async def promote_candidate(candidate_id: int):
    """
    将指定候选晋升为正式人物事实。
    正式事实仍保留来源信息。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                person_id,
                category,
                fact_key,
                fact_value,
                confidence,
                source_platform,
                source_chat_id,
                source_message_id,
                status
            FROM memory_candidates
            WHERE id=?
            """,
            (candidate_id,)
        )

        row = await cur.fetchone()

    if not row:
        return False

    (
        person_id,
        category,
        fact_key,
        fact_value,
        confidence,
        source_platform,
        source_chat_id,
        source_message_id,
        status
    ) = row

    if status != "pending":
        return False

    await add_fact(
        person_id=person_id,
        category=category,
        fact_key=fact_key,
        fact_value=fact_value,
        confidence=confidence,
        source_platform=source_platform,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE memory_candidates
            SET status='promoted',
                reviewed_at=?
            WHERE id=?
            """,
            (now(), candidate_id)
        )

        await db.commit()

    return True


async def reject_candidate(candidate_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE memory_candidates
            SET status='rejected',
                reviewed_at=?
            WHERE id=?
              AND status='pending'
            """,
            (now(), candidate_id)
        )

        await db.commit()

        return cur.rowcount > 0


async def get_pending(person_id=None, limit=50):
    async with aiosqlite.connect(DB_PATH) as db:

        if person_id is None:
            cur = await db.execute(
                """
                SELECT
                    id,
                    person_id,
                    category,
                    fact_key,
                    fact_value,
                    confidence,
                    source_text
                FROM memory_candidates
                WHERE status='pending'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,)
            )
        else:
            cur = await db.execute(
                """
                SELECT
                    id,
                    person_id,
                    category,
                    fact_key,
                    fact_value,
                    confidence,
                    source_text
                FROM memory_candidates
                WHERE status='pending'
                  AND person_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (person_id, limit)
            )

        return await cur.fetchall()
