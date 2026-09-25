import aiosqlite

from app.config import DB_PATH
from app.memory.reviewer import promote_candidate


# 这些类别允许自动成为长期资料
STABLE_CATEGORIES = {
    "identity",
    "preference",
    "habit",
    "relationship",
    "learning",
    "work",
    "location",
    "device",
    "account",
    "other",
}

# 明确要求系统记住
EXPLICIT_MEMORY_WORDS = (
    "记住",
    "记一下",
    "记得",
    "以后记得",
    "别忘了",
)

# 明显临时状态，不自动长期保存
TEMPORARY_WORDS = (
    "今天",
    "今晚",
    "刚刚",
    "刚才",
    "现在",
    "目前",
    "这会儿",
    "等会",
    "一会儿",
)


def explicitly_requested(source_text: str) -> bool:
    text = source_text or ""

    return any(
        word in text
        for word in EXPLICIT_MEMORY_WORDS
    )


def looks_temporary(source_text: str) -> bool:
    text = source_text or ""

    return any(
        word in text
        for word in TEMPORARY_WORDS
    )


async def matching_evidence_count(
    *,
    person_id: int,
    category: str,
    fact_key: str,
    fact_value: str,
    source_platform=None,
    source_chat_id=None,
) -> int:
    """
    读取同一 pending 事实累计的证据次数。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT evidence_count
            FROM memory_candidates
            WHERE person_id=?
              AND category=?
              AND fact_key=?
              AND fact_value=?
              AND source_platform IS ?
              AND source_chat_id IS ?
              AND status='pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                person_id,
                category,
                fact_key,
                fact_value,
                source_platform,
                str(source_chat_id)
                    if source_chat_id is not None
                    else None,
            )
        )

        row = await cur.fetchone()

    return int(row[0] or 0) if row else 0


async def evaluate_candidate(candidate_id: int):
    """
    返回：
      promoted
      pending
      rejected
      missing
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
                source_text,
                status,
                source_platform,
                source_chat_id
            FROM memory_candidates
            WHERE id=?
            """,
            (candidate_id,)
        )

        row = await cur.fetchone()

    if not row:
        return "missing"

    (
        person_id,
        category,
        fact_key,
        fact_value,
        confidence,
        source_text,
        status,
        source_platform,
        source_chat_id,
    ) = row

    if status != "pending":
        return status

    confidence = float(confidence or 0)

    # 模型自己都不确定的内容，不进入长期记忆
    if confidence < 0.70:
        return "pending"

    # 不认识的类别先留给人工/未来策略处理
    if category not in STABLE_CATEGORIES:
        return "pending"

    # 用户明确要求记住 + 高可信
    if (
        explicitly_requested(source_text)
        and confidence >= 0.85
    ):
        ok = await promote_candidate(candidate_id)
        return "promoted" if ok else "pending"

    # 带明显临时语义的内容不自动晋升
    if looks_temporary(source_text):
        return "pending"

    # 极高可信稳定事实，可以直接晋升
    if confidence >= 0.97:
        ok = await promote_candidate(candidate_id)
        return "promoted" if ok else "pending"

    # 普通事实至少需要两份独立候选证据
    evidence = await matching_evidence_count(
        person_id=person_id,
        category=category,
        fact_key=fact_key,
        fact_value=fact_value,
        source_platform=source_platform,
        source_chat_id=source_chat_id,
    )

    if confidence >= 0.85 and evidence >= 2:
        ok = await promote_candidate(candidate_id)
        return "promoted" if ok else "pending"

    return "pending"


async def review_pending_candidates(
    person_id=None,
    limit=100,
):
    async with aiosqlite.connect(DB_PATH) as db:

        if person_id is None:
            cur = await db.execute(
                """
                SELECT id
                FROM memory_candidates
                WHERE status='pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,)
            )

        else:
            cur = await db.execute(
                """
                SELECT id
                FROM memory_candidates
                WHERE status='pending'
                  AND person_id=?
                ORDER BY id ASC
                LIMIT ?
                """,
                (person_id, limit)
            )

        rows = await cur.fetchall()

    result = {
        "promoted": 0,
        "pending": 0,
        "rejected": 0,
        "missing": 0,
    }

    for (candidate_id,) in rows:
        status = await evaluate_candidate(
            candidate_id
        )

        if status in result:
            result[status] += 1
        else:
            result["pending"] += 1

    return result
