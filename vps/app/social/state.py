import aiosqlite
from datetime import datetime, timezone

from app.config import DB_PATH


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_state_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS relationship_state (
            person_id INTEGER PRIMARY KEY,

            familiarity REAL NOT NULL DEFAULT 0.0,
            trust REAL NOT NULL DEFAULT 0.0,
            closeness REAL NOT NULL DEFAULT 0.0,
            attachment REAL NOT NULL DEFAULT 0.0,

            interaction_count INTEGER NOT NULL DEFAULT 0,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            FOREIGN KEY(person_id)
                REFERENCES people(person_id)
        );

        CREATE TABLE IF NOT EXISTS emotion_state (
            person_id INTEGER PRIMARY KEY,

            mood TEXT NOT NULL DEFAULT 'neutral',

            valence REAL NOT NULL DEFAULT 0.0,
            arousal REAL NOT NULL DEFAULT 0.0,

            intensity REAL NOT NULL DEFAULT 0.0,

            reason TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            FOREIGN KEY(person_id)
                REFERENCES people(person_id)
        );

        CREATE TABLE IF NOT EXISTS state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            person_id INTEGER NOT NULL,
            state_type TEXT NOT NULL,

            old_value TEXT,
            new_value TEXT,

            reason TEXT,

            source_platform TEXT,
            source_chat_id TEXT,
            source_message_id INTEGER,

            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_state_history_person
        ON state_history(person_id, created_at);
        """)

        await db.commit()


async def ensure_person_state(person_id: int):
    t = now()

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            INSERT OR IGNORE INTO relationship_state (
                person_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?)
            """,
            (person_id, t, t)
        )
        # OWNER 是长期熟悉的搭档，新状态保留已有相处的熟悉度。
        # 只在尚未发生任何互动时设定一次基础值；之后的细微关系波动仍由真实互动驱动。
        await db.execute("""
            UPDATE relationship_state
            SET familiarity=MAX(familiarity, 95.0),
                trust=MAX(trust, 95.0),
                closeness=MAX(closeness, 95.0),
                attachment=MAX(attachment, 95.0)
            WHERE person_id=?
              AND interaction_count=0
              AND EXISTS (
                  SELECT 1 FROM people
                  WHERE people.person_id=?
                    AND people.role='OWNER'
              )
        """, (person_id, person_id))

        await db.execute("""
            UPDATE relationship_state
            SET attachment=60.0
            WHERE person_id=?
              AND attachment < 60.0
              AND EXISTS (
                  SELECT 1 FROM people
                  WHERE people.person_id=?
                    AND people.role='OWNER'
              )
        """, (person_id, person_id))

        # 非 OWNER 没有 OWNER 专属的依恋度。
        # 即使旧版本数据、误写或未来其他模块写入，也会被这里归零。
        await db.execute("""
            UPDATE relationship_state
            SET attachment=0.0,
                closeness=MIN(closeness, 88.0),
                trust=MIN(trust, 92.0)
            WHERE person_id=?
              AND EXISTS (
                  SELECT 1 FROM people
                  WHERE people.person_id=?
                    AND people.role!='OWNER'
              )
        """, (person_id, person_id))

        await db.execute(
            """
            INSERT OR IGNORE INTO emotion_state (
                person_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?)
            """,
            (person_id, t, t)
        )

        await db.commit()


async def get_relationship_state(person_id: int):
    await ensure_person_state(person_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                familiarity,
                trust,
                closeness,
                attachment,
                interaction_count,
                updated_at
            FROM relationship_state
            WHERE person_id=?
            """,
            (person_id,)
        )

        row = await cur.fetchone()

    return {
        "familiarity": row[0],
        "trust": row[1],
        "closeness": row[2],
        "attachment": row[3],
        "interaction_count": row[4],
        "updated_at": row[5],
    }


async def get_emotion_state(person_id: int):
    await ensure_person_state(person_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                mood,
                valence,
                arousal,
                intensity,
                reason,
                updated_at
            FROM emotion_state
            WHERE person_id=?
            """,
            (person_id,)
        )

        row = await cur.fetchone()

    return {
        "mood": row[0],
        "valence": row[1],
        "arousal": row[2],
        "intensity": row[3],
        "reason": row[4],
        "updated_at": row[5],
    }


async def build_state_context(person_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT role FROM people WHERE person_id=?", (person_id,))
        row = await cur.fetchone()
        is_owner = bool(row and row[0] == "OWNER")

    relationship = await get_relationship_state(
        person_id
    )

    emotion = await get_emotion_state(
        person_id
    )

    return {
        "relationship": relationship,
        "primary_bond": is_owner,
        "semantic": build_relationship_semantic(relationship, is_owner),
        "emotion": emotion,
    }

def relationship_level(value: float) -> str:
    if value < 20:
        return "low"
    if value < 50:
        return "developing"
    if value < 75:
        return "strong"
    if value < 90:
        return "deep"
    return "very_deep"

def build_relationship_semantic(relationship: dict, is_owner: bool) -> dict:
    result = {
        "primary_bond": is_owner,
        "stage": relationship_stage(
            relationship,
            is_owner,
        ),
        "familiarity": relationship_level(relationship["familiarity"]),
        "trust": relationship_level(relationship["trust"]),
        "closeness": relationship_level(relationship["closeness"]),
    }

    if is_owner:
        result["attachment"] = relationship_level(
            relationship["attachment"]
        )

    return result


def relationship_stage(
    relationship: dict,
    is_owner: bool,
) -> str:
    familiarity = relationship["familiarity"]
    trust = relationship["trust"]
    closeness = relationship["closeness"]
    attachment = relationship.get("attachment", 0.0)

    if not is_owner:
        # 非 OWNER 的关系只沿友情轴发展。
        # 不读取 attachment，也不允许进入恋爱/暧昧阶段。
        if familiarity < 20:
            return "陌生"
        if familiarity < 50:
            return "熟悉"
        if familiarity < 85:
            return "朋友"
        return "关系好的朋友"

    if familiarity < 20:
        return "刚开始熟悉"

    if trust < 35 or closeness < 35:
        return "逐渐熟悉"

    if trust < 60 or closeness < 60:
        return "明显亲近"

    if closeness < 80:
        return "亲密"

    if (
        closeness >= 95
        and trust >= 95
        and attachment >= 95
    ):
        return "最熟的搭档"

    if (
        closeness >= 90
        and trust >= 90
        and attachment >= 85
    ):
        return "几乎没有距离"

    if attachment >= 70 and trust >= 75:
        return "深度亲密"

    return "很亲密"
