import json
from datetime import datetime, timezone
import aiosqlite

from app.config import DB_PATH
from app.social.state import (
    now,
    ensure_person_state,
    get_emotion_state,
)


def clamp(value, minimum=0.0, maximum=100.0):
    return max(
        minimum,
        min(maximum, float(value))
    )


async def register_interaction(
    *,
    person_id: int,
    source_platform=None,
    source_chat_id=None,
    source_message_id=None,
):
    """
    登记一次真实互动。

    同一 source message 只能影响关系一次。
    检查、关系更新、历史写入位于同一个事务中，
    防止并发重复增加 familiarity / interaction_count。
    """
    await ensure_person_state(person_id)

    source_chat = (
        str(source_chat_id)
        if source_chat_id is not None
        else None
    )

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            # SQLite 写锁：让“检查 -> 更新 -> 写历史”成为原子操作。
            await db.execute("BEGIN IMMEDIATE")

            if source_message_id is not None:
                cur = await db.execute(
                    """
                    SELECT 1
                    FROM state_history
                    WHERE person_id=?
                      AND state_type='relationship'
                      AND source_platform IS ?
                      AND source_chat_id IS ?
                      AND source_message_id=?
                      AND reason='real_interaction'
                    LIMIT 1
                    """,
                    (
                        person_id,
                        source_platform,
                        source_chat,
                        source_message_id,
                    )
                )

                if await cur.fetchone():
                    cur = await db.execute(
                        """
                        SELECT
                            familiarity,
                            trust,
                            closeness,
                            attachment,
                            interaction_count
                        FROM relationship_state
                        WHERE person_id=?
                        """,
                        (person_id,)
                    )
                    row = await cur.fetchone()

                    await db.commit()

                    return {
                        "familiarity": row[0],
                        "trust": row[1],
                        "closeness": row[2],
                        "attachment": row[3],
                        "interaction_count": row[4],
                    }

            cur = await db.execute(
                """
                SELECT
                    familiarity,
                    trust,
                    closeness,
                    attachment,
                    interaction_count
                FROM relationship_state
                WHERE person_id=?
                """,
                (person_id,)
            )
            row = await cur.fetchone()

            if row is None:
                raise RuntimeError(
                    f"relationship_state missing for person_id={person_id}"
                )

            old = {
                "familiarity": row[0],
                "trust": row[1],
                "closeness": row[2],
                "attachment": row[3],
                "interaction_count": row[4],
            }

            count = old["interaction_count"] + 1

            familiarity_gain = max(
                0.03,
                0.35 * (
                    1.0
                    - old["familiarity"] / 100.0
                )
            )

            familiarity = clamp(
                old["familiarity"] + familiarity_gain
            )

            new = {
                "familiarity": familiarity,
                "trust": old["trust"],
                "closeness": old["closeness"],
                "attachment": old["attachment"],
                "interaction_count": count,
            }

            t = now()

            await db.execute(
                """
                UPDATE relationship_state
                SET familiarity=?,
                    interaction_count=?,
                    updated_at=?
                WHERE person_id=?
                """,
                (
                    familiarity,
                    count,
                    t,
                    person_id,
                )
            )

            await db.execute(
                """
                INSERT INTO state_history (
                    person_id,
                    state_type,
                    old_value,
                    new_value,
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
                    "relationship",
                    json.dumps(
                        old,
                        ensure_ascii=False
                    ),
                    json.dumps(
                        new,
                        ensure_ascii=False
                    ),
                    "real_interaction",
                    source_platform,
                    source_chat,
                    source_message_id,
                    t,
                )
            )

            await db.commit()
            return new

        except Exception:
            await db.rollback()
            raise



def clamp_emotion(value, minimum=-1.0, maximum=1.0):
    return max(
        minimum,
        min(maximum, float(value))
    )

def clamp_unit(value):
    return max(
        0.0,
        min(1.0, float(value))
    )

def derive_mood(valence: float, arousal: float, intensity: float) -> str:
    if intensity < 0.15:
        return "neutral"

    if valence >= 0.35:
        if arousal >= 0.55:
            return "happy"
        return "content"

    if valence <= -0.35:
        if arousal >= 0.65:
            return "upset"
        if arousal >= 0.35:
            return "sad"
        return "low"

    if arousal >= 0.70:
        return "restless"

    if valence < -0.05:
        return "uneasy"

    return "calm"

def emotion_delta(event_type: str):
    rules = {
        "comfort_received": {
            "valence": 0.18,
            "arousal": -0.10,
            "intensity": 0.08,
        },
        "expectation_fulfilled": {
            "valence": 0.12,
            "arousal": 0.04,
            "intensity": 0.06,
        },
        "expectation_missed": {
            "valence": -0.18,
            "arousal": 0.12,
            "intensity": 0.15,
        },
        "game_win": {
            "valence": 0.10,
            "arousal": 0.08,
            "intensity": 0.06,
        },
        "game_loss": {
            "valence": -0.08,
            "arousal": 0.07,
            "intensity": 0.07,
        },
        "argument_pressure": {
            "valence": -0.15,
            "arousal": 0.18,
            "intensity": 0.16,
        },
    }
    return rules.get(event_type)

async def apply_emotion_event(
    *,
    person_id: int,
    event_type: str,
    reason=None,
):
    delta = emotion_delta(event_type)

    if delta is None:
        return None

    await ensure_person_state(person_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT mood, valence, arousal, intensity
            FROM emotion_state
            WHERE person_id=?
            """,
            (person_id,)
        )
        row = await cur.fetchone()

    old = {
        "mood": row[0],
        "valence": row[1],
        "arousal": row[2],
        "intensity": row[3],
    }

    valence = clamp_emotion(
        old["valence"] + delta["valence"]
    )
    arousal = clamp_unit(
        old["arousal"] + delta["arousal"]
    )
    intensity = clamp_unit(
        old["intensity"] + delta["intensity"]
    )

    new = {
        "mood": derive_mood(valence, arousal, intensity),
        "valence": valence,
        "arousal": arousal,
        "intensity": intensity,
        "reason": reason or event_type,
    }

    t = now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE emotion_state
            SET mood=?,
                valence=?,
                arousal=?,
                intensity=?,
                reason=?,
                updated_at=?
            WHERE person_id=?
            """,
            (
                new["mood"],
                new["valence"],
                new["arousal"],
                new["intensity"],
                new["reason"],
                t,
                person_id,
            )
        )
        await db.execute(
            """
            INSERT INTO state_history (
                person_id, state_type,
                old_value, new_value,
                reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                "emotion",
                json.dumps(old, ensure_ascii=False),
                json.dumps(new, ensure_ascii=False),
                event_type,
                t,
            )
        )

        await db.commit()

    return new

def decay_emotion_values(
    valence: float,
    arousal: float,
    intensity: float,
    elapsed_hours: float,
):
    hours = max(0.0, float(elapsed_hours))

    valence *= 0.92 ** hours
    arousal *= 0.75 ** hours
    intensity *= 0.82 ** hours

    if abs(valence) < 0.02:
        valence = 0.0
    if arousal < 0.02:
        arousal = 0.0
    if intensity < 0.02:
        intensity = 0.0

    return {
        "valence": clamp_emotion(valence),
        "arousal": clamp_unit(arousal),
        "intensity": clamp_unit(intensity),
    }

def elapsed_hours_since(updated_at: str) -> float:
    if not updated_at:
        return 0.0

    previous = datetime.fromisoformat(updated_at)

    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)

    current = datetime.now(timezone.utc)

    return max(
        0.0,
        (current - previous).total_seconds() / 3600.0
    )

async def get_current_emotion(person_id: int):
    raw = await get_emotion_state(person_id)

    hours = elapsed_hours_since(raw["updated_at"])

    decayed = decay_emotion_values(
        raw["valence"],
        raw["arousal"],
        raw["intensity"],
        hours,
    )

    return {
        "mood": derive_mood(
            decayed["valence"],
            decayed["arousal"],
            decayed["intensity"],
        ),
        "valence": decayed["valence"],
        "arousal": decayed["arousal"],
        "intensity": decayed["intensity"],
        "reason": raw["reason"],
        "updated_at": raw["updated_at"],
    }

def build_emotion_semantic(emotion: dict) -> dict:
    mood_map = {
        "neutral": "平静",
        "calm": "放松",
        "content": "愉快",
        "happy": "开心",
        "uneasy": "有些不安",
        "low": "有些低落",
        "sad": "难过",
        "upset": "明显难受",
        "restless": "有些躁动",
    }

    intensity = float(emotion["intensity"])

    if intensity < 0.15:
        strength = "很轻"
    elif intensity < 0.35:
        strength = "轻微"
    elif intensity < 0.65:
        strength = "明显"
    else:
        strength = "强烈"

    reason_map = {
        "interaction:comfort_received": "刚被安慰过，情绪余波偏暖",
        "interaction:shared_important_moment": "刚经历了一个有意义的共同约定",
        "interaction:argument_pressure": "刚被强硬或攻击性的表达刺激过",
        "reminder_delivered": "刚完成了一件答应提醒的事",
    }

    return {
        "mood": mood_map.get(
            emotion["mood"],
            emotion["mood"],
        ),
        "strength": strength,
        "residue": reason_map.get(
            emotion.get("reason"),
            "",
        ),
    }
