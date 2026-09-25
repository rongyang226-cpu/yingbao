from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_time(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(str(value))

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def maintain_long_term_memory():
    """
    自然记忆维护：
    - 30天内不衰减
    - 多次强化的事实长期保留
    - 普通事实长期未强化后缓慢淡化
    - 淡出只 active=0，不删除
    """

    now = _utcnow()

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS memory_maintenance_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        cur = await db.execute("""
            SELECT value
            FROM memory_maintenance_state
            WHERE key='last_daily_run'
        """)

        row = await cur.fetchone()

        today = now.date().isoformat()

        if row and row[0] == today:
            return {
                "weakened": 0,
                "faded": 0,
                "skipped": True,
            }

        cur = await db.execute("""
            SELECT
                id,
                confidence,
                strength,
                reinforcement_count,
                last_reinforced_at,
                updated_at
            FROM person_facts
            WHERE active = 1
        """)

        rows = await cur.fetchall()

        weakened = 0
        faded = 0

        for (
            fact_id,
            confidence,
            strength,
            reinforcement_count,
            last_reinforced_at,
            updated_at,
        ) in rows:

            confidence = float(confidence or 0)
            strength = float(
                strength if strength is not None else 1.0
            )
            reinforcement_count = int(
                reinforcement_count or 1
            )

            last_time = (
                _parse_time(last_reinforced_at)
                or _parse_time(updated_at)
            )

            if not last_time:
                continue

            age_days = (
                now - last_time
            ).total_seconds() / 86400

            if age_days <= 30:
                continue

            if reinforcement_count >= 3:
                continue

            if confidence >= 0.97:
                decay = 0.001
            elif age_days <= 90:
                decay = 0.003
            else:
                decay = 0.005

            new_strength = max(
                0.0,
                strength - decay
            )

            should_fade = (
                age_days >= 120
                and new_strength < 0.35
                and confidence < 0.95
                and reinforcement_count < 3
            )

            if should_fade:
                await db.execute("""
                    UPDATE person_facts
                    SET
                        strength=?,
                        active=0,
                        updated_at=?
                    WHERE id=?
                """, (
                    new_strength,
                    now.isoformat(),
                    fact_id,
                ))

                faded += 1

            elif new_strength != strength:
                await db.execute("""
                    UPDATE person_facts
                    SET strength=?
                    WHERE id=?
                """, (
                    new_strength,
                    fact_id,
                ))

                weakened += 1

        await db.execute("""
            INSERT INTO memory_maintenance_state (
                key,
                value
            )
            VALUES ('last_daily_run', ?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
        """, (today,))

        await db.commit()

    return {
        "weakened": weakened,
        "faded": faded,
        "skipped": False,
    }
