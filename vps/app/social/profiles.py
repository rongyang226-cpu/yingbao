import aiosqlite
from datetime import datetime, timezone

from app.config import DB_PATH


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_profile_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS person_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            person_id INTEGER NOT NULL,

            category TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value TEXT NOT NULL,

            confidence REAL NOT NULL DEFAULT 1.0,

            source_platform TEXT,
            source_chat_id TEXT,
            source_message_id INTEGER,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            active INTEGER NOT NULL DEFAULT 1,

            FOREIGN KEY(person_id)
                REFERENCES people(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_person_facts_person
        ON person_facts(person_id, active);

        CREATE TABLE IF NOT EXISTS person_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            person_id INTEGER NOT NULL,
            note TEXT NOT NULL,

            source_platform TEXT,
            source_chat_id TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY(person_id)
                REFERENCES people(person_id)
        );
        """)

        await db.commit()


async def add_fact(
    person_id,
    category,
    fact_key,
    fact_value,
    confidence=1.0,
    source_platform=None,
    source_chat_id=None,
    source_message_id=None
):
    """
    长期事实写入：

    - 同 key + 同 value 再次出现：强化已有记忆，不重复插入。
    - 同 key 但 value 改变：旧版本失效，新版本成为当前事实。
    - 历史版本不物理删除。
    """
    t = now()

    async with aiosqlite.connect(DB_PATH) as db:

        cur = await db.execute(
            """
            SELECT
                id,
                fact_value,
                confidence,
                strength,
                reinforcement_count
            FROM person_facts
            WHERE person_id=?
              AND category=?
              AND fact_key=?
              AND source_platform IS ?
              AND source_chat_id IS ?
              AND active=1
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                person_id,
                category,
                fact_key,
                source_platform,
                str(source_chat_id)
                    if source_chat_id is not None
                    else None,
            )
        )

        existing = await cur.fetchone()

        if existing:
            (
                fact_id,
                old_value,
                old_confidence,
                strength,
                reinforcement_count,
            ) = existing

            # 完全相同的长期事实再次出现：强化。
            if str(old_value).strip() == str(fact_value).strip():

                old_confidence = float(old_confidence or 0)
                strength = float(
                    strength if strength is not None else 1.0
                )
                reinforcement_count = int(
                    reinforcement_count or 1
                )

                # 每次真实重复证据轻微加强，最高保持1.0。
                new_strength = min(
                    1.0,
                    strength + 0.08
                )

                new_confidence = max(
                    old_confidence,
                    float(confidence or 0)
                )

                await db.execute(
                    """
                    UPDATE person_facts
                    SET
                        confidence=?,
                        strength=?,
                        reinforcement_count=?,
                        last_reinforced_at=?,
                        updated_at=?,
                        source_platform=?,
                        source_chat_id=?,
                        source_message_id=?
                    WHERE id=?
                    """,
                    (
                        new_confidence,
                        new_strength,
                        reinforcement_count + 1,
                        t,
                        t,
                        source_platform,
                        str(source_chat_id)
                            if source_chat_id is not None
                            else None,
                        source_message_id,
                        fact_id,
                    )
                )

                await db.commit()
                return

            # 同一个事实键产生了新版本：
            # 旧版本保留但退出当前记忆。
            await db.execute(
                """
                UPDATE person_facts
                SET active=0,
                    updated_at=?
                WHERE id=?
                """,
                (
                    t,
                    fact_id,
                )
            )

        await db.execute(
            """
            INSERT INTO person_facts (
                person_id,
                category,
                fact_key,
                fact_value,
                confidence,
                source_platform,
                source_chat_id,
                source_message_id,
                created_at,
                updated_at,
                active,
                strength,
                reinforcement_count,
                last_reinforced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1.0, 1, ?)
            """,
            (
                person_id,
                category,
                fact_key,
                fact_value,
                confidence,
                source_platform,
                str(source_chat_id)
                    if source_chat_id is not None
                    else None,
                source_message_id,
                t,
                t,
                t,
            )
        )

        await db.commit()


async def get_active_facts(
    person_id,
    *,
    source_chat_id=None,
    strict_scope=False,
):
    conditions = [
        "person_id=?",
        "active=1",
    ]
    params = [person_id]

    if strict_scope:
        conditions.append(
            "source_chat_id=?"
        )
        params.append(
            str(source_chat_id)
            if source_chat_id is not None
            else None
        )

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            f"""
            SELECT
                category,
                fact_key,
                fact_value,
                confidence,
                source_chat_id
            FROM person_facts
            WHERE {' AND '.join(conditions)}
            ORDER BY updated_at DESC
            """,
            params,
        )

        rows = await cur.fetchall()

    return [
        {
            "category": category,
            "key": key,
            "value": value,
            "confidence": confidence,
            "source_chat_id": source_chat,
        }
        for category, key, value, confidence, source_chat in rows
    ]


async def build_profile_context(
    person_id,
    role="USER",
    *,
    current_chat_id=None,
    current_chat_type=None,
):
    # 群聊人物资料严格按当前群隔离。
    # 私聊也只读取当前私聊来源；OWNER 私聊例外，可读取自己的完整档案。
    is_group = current_chat_type in ("group", "supergroup")
    strict_scope = is_group or role != "OWNER"

    facts = await get_active_facts(
        person_id,
        source_chat_id=current_chat_id,
        strict_scope=strict_scope,
    )

    if not facts:
        return "当前没有在这个聊天场景中已确认的人物长期资料。"

    if role == "OWNER" and not is_group:
        max_facts = 30
    else:
        max_facts = 8

    lines = []

    for fact in facts[:max_facts]:
        category = fact["category"]
        key = fact["key"]
        value = fact["value"]
        confidence = fact["confidence"]

        lines.append(
            f"- [{category}] {key}: {value} "
            f"(confidence={confidence:.2f})"
        )

    return "\n".join(lines)
