from app.social.state_engine import clamp


OWNER_BASE_ATTACHMENT = 60.0


def relationship_delta(event_type: str):
    rules = {
        "expectation_fulfilled": {
            "trust": 0.30,
            "closeness": 0.20,
            "attachment": 0.15,
        },
        "comfort_received": {
            "trust": 0.15,
            "closeness": 0.30,
            "attachment": 0.20,
        },
        "owner_returned": {
            "closeness": 0.10,
            "attachment": 0.08,
        },
        "shared_important_moment": {
            "trust": 0.10,
            "closeness": 0.20,
            "attachment": 0.10,
        },
    }

    return rules.get(event_type)


def apply_delta(state: dict, delta: dict):
    result = dict(state)

    for key in ("trust", "closeness", "attachment"):
        if key not in delta:
            continue

        current = float(state[key])

        # 关系越深，正向增长越慢。
        # 低关系阶段接近完整收益；
        # 接近100时只产生很小变化。
        gain = float(delta[key])

        if gain > 0:
            gain *= max(
                0.10,
                1.0 - current / 100.0
            )

        result[key] = clamp(current + gain)

    return result


import json
import aiosqlite

from app.config import DB_PATH
from app.social.state import now, ensure_person_state


async def apply_bond_event(
    *,
    person_id: int,
    event_type: str,
    source_platform=None,
    source_chat_id=None,
    source_message_id=None,
):
    delta = relationship_delta(event_type)

    if delta is None:
        return None

    # 核心依赖事件只属于 OWNER。
    # 普通群友不能通过互动获得 OWNER bond。
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT role FROM people WHERE person_id=?",
            (person_id,)
        )
        person = await cur.fetchone()

    if not person or person[0] != "OWNER":
        return None

    await ensure_person_state(person_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT familiarity, trust, closeness,
                   attachment, interaction_count
            FROM relationship_state
            WHERE person_id=?
            """,
            (person_id,)
        )
        row = await cur.fetchone()

        old = {
            "familiarity": row[0],
            "trust": row[1],
            "closeness": row[2],
            "attachment": row[3],
            "interaction_count": row[4],
        }

        new = apply_delta(old, delta)
        t = now()

        await db.execute(
            """
            UPDATE relationship_state
            SET trust=?,
                closeness=?,
                attachment=?,
                updated_at=?
            WHERE person_id=?
            """,
            (
                new["trust"],
                new["closeness"],
                new["attachment"],
                t,
                person_id,
            )
        )

        await db.execute(
            """
            INSERT INTO state_history (
                person_id, state_type,
                old_value, new_value,
                reason,
                source_platform,
                source_chat_id,
                source_message_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                "bond",
                json.dumps(old, ensure_ascii=False),
                json.dumps(new, ensure_ascii=False),
                event_type,
                source_platform,
                str(source_chat_id)
                    if source_chat_id is not None
                    else None,
                source_message_id,
                t,
            )
        )

        await db.commit()

    return new
