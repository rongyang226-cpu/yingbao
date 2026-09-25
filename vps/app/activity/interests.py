from __future__ import annotations

import math
import random
from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


DEFAULT_INTERESTS = {
    ("game", "2048"): 0.52,
    ("game", "chess"): 0.56,
    ("game", "gomoku"): 0.54,
    ("game", "jump_jump"): 0.46,
    ("game", "match3"): 0.50,
    ("game", "go"): 0.58,
    ("sim_game", "Minecraft"): 0.58,
    ("sim_game", "崩坏：星穹铁道"): 0.55,
    ("sim_game", "Muse Dash"): 0.50,
    ("activity", "reading"): 0.60,
    ("activity", "listening"): 0.57,
    ("activity", "walking"): 0.54,
    ("activity", "coffee"): 0.48,
    ("activity", "organizing"): 0.44,
    ("activity", "shopping"): 0.42,
    ("activity", "gaming"): 0.62,
    ("activity", "resting"): 0.50,
}


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_interest_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS ying_interests (
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            affinity REAL NOT NULL DEFAULT 0.5,
            boredom REAL NOT NULL DEFAULT 0.0,
            exposures INTEGER NOT NULL DEFAULT 0,
            positive_events INTEGER NOT NULL DEFAULT 0,
            negative_events INTEGER NOT NULL DEFAULT 0,
            last_event TEXT,
            last_seen_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(kind, name)
        );

        CREATE TABLE IF NOT EXISTS ying_interest_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            old_affinity REAL NOT NULL,
            new_affinity REAL NOT NULL,
            old_boredom REAL NOT NULL,
            new_boredom REAL NOT NULL,
            event TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)

        t = now()
        for (kind, name), affinity in DEFAULT_INTERESTS.items():
            await db.execute(
                """
                INSERT OR IGNORE INTO ying_interests (
                    kind, name, affinity, boredom, updated_at
                )
                VALUES (?, ?, ?, 0.0, ?)
                """,
                (kind, name, float(affinity), t),
            )

        await db.commit()


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))


def _event_delta(event: str):
    return {
        "great": (0.045, -0.08),
        "good": (0.022, -0.04),
        "neutral": (0.002, 0.035),
        "mixed": (-0.006, 0.055),
        "bad": (-0.020, 0.070),
        "frustrating": (-0.032, 0.085),
        "completed": (0.008, 0.025),
    }.get(str(event), (0.0, 0.02))
async def get_interest(kind: str, name: str):
    await init_interest_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT affinity, boredom, exposures,
                   positive_events, negative_events,
                   last_event, last_seen_at
            FROM ying_interests
            WHERE kind=? AND name=?
            """,
            (str(kind), str(name)),
        )
        row = await cur.fetchone()

    if not row:
        return {
            "affinity": 0.5,
            "boredom": 0.0,
            "exposures": 0,
            "positive_events": 0,
            "negative_events": 0,
            "last_event": None,
            "last_seen_at": None,
        }

    return {
        "affinity": float(row[0]),
        "boredom": float(row[1]),
        "exposures": int(row[2]),
        "positive_events": int(row[3]),
        "negative_events": int(row[4]),
        "last_event": row[5],
        "last_seen_at": row[6],
    }


async def record_interest_event(
    *,
    kind: str,
    name: str,
    event: str,
):
    await init_interest_db()

    current = await get_interest(kind, name)
    old_affinity = current["affinity"]
    old_boredom = current["boredom"]

    affinity_delta, boredom_delta = _event_delta(event)

    # 越接近极端，变化越慢，避免几次结果就变成“最爱/最讨厌”。
    if affinity_delta > 0:
        affinity_delta *= max(0.18, 1.0 - old_affinity)
    else:
        affinity_delta *= max(0.18, old_affinity)

    new_affinity = _clamp(old_affinity + affinity_delta)
    new_boredom = _clamp(old_boredom + boredom_delta)

    positive = int(event in {"great", "good", "completed"})
    negative = int(event in {"bad", "frustrating"})

    t = now()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE ying_interests
            SET affinity=?,
                boredom=?,
                exposures=exposures+1,
                positive_events=positive_events+?,
                negative_events=negative_events+?,
                last_event=?,
                last_seen_at=?,
                updated_at=?
            WHERE kind=? AND name=?
            """,
            (
                new_affinity,
                new_boredom,
                positive,
                negative,
                str(event),
                t,
                t,
                str(kind),
                str(name),
            ),
        )

        await db.execute(
            """
            INSERT INTO ying_interest_history (
                kind, name,
                old_affinity, new_affinity,
                old_boredom, new_boredom,
                event, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(kind),
                str(name),
                old_affinity,
                new_affinity,
                old_boredom,
                new_boredom,
                str(event),
                t,
            ),
        )
        await db.commit()

    return {
        "affinity": new_affinity,
        "boredom": new_boredom,
    }
async def relax_boredom(kind: str | None = None):
    """
    时间过去后，腻味感会慢慢消退。
    主生活循环偶尔调用即可。
    """
    await init_interest_db()

    async with aiosqlite.connect(DB_PATH) as db:
        if kind:
            await db.execute(
                """
                UPDATE ying_interests
                SET boredom=MAX(0.0, boredom*0.94),
                    updated_at=?
                WHERE kind=?
                """,
                (now(), str(kind)),
            )
        else:
            await db.execute(
                """
                UPDATE ying_interests
                SET boredom=MAX(0.0, boredom*0.97),
                    updated_at=?
                """,
                (now(),),
            )
        await db.commit()


async def weighted_choice(kind: str, names):
    names = list(names)
    if not names:
        raise ValueError("empty interest pool")

    await init_interest_db()

    weights = []
    for name in names:
        state = await get_interest(kind, name)

        # affinity 决定长期偏好，boredom 压低刚玩腻的项目；
        # 始终留一点随机性，不变成固定最爱循环。
        weight = (
            0.20
            + state["affinity"] * 1.55
            - state["boredom"] * 0.90
        )
        weights.append(max(0.06, weight))

    return random.choices(
        names,
        weights=weights,
        k=1,
    )[0]


async def build_interest_context():
    await init_interest_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT kind, name, affinity, boredom,
                   exposures, last_event
            FROM ying_interests
            ORDER BY affinity DESC, exposures DESC
            """
        )
        rows = await cur.fetchall()

    likes = []
    dislikes = []
    temporary_bored = []

    for kind, name, affinity, boredom, exposures, last_event in rows:
        affinity = float(affinity)
        boredom = float(boredom)
        exposures = int(exposures)

        if exposures >= 3 and affinity >= 0.62:
            likes.append((affinity, name, kind))

        if exposures >= 4 and affinity <= 0.36:
            dislikes.append((affinity, name, kind))

        if exposures >= 2 and boredom >= 0.42:
            temporary_bored.append((boredom, name, kind))

    def take(items, reverse=True, n=5):
        return [
            x[1]
            for x in sorted(
                items,
                key=lambda x: x[0],
                reverse=reverse,
            )[:n]
        ]

    like_names = take(likes, True, 5)
    dislike_names = take(dislikes, False, 4)
    bored_names = take(temporary_bored, True, 4)

    lines = []

    if like_names:
        lines.append(
            "最近逐渐形成的偏好：" + "、".join(like_names)
        )
    else:
        lines.append(
            "目前还没有经过足够经历形成很明确的长期最爱。"
        )

    if dislike_names:
        lines.append(
            "长期兴趣偏低：" + "、".join(dislike_names)
        )

    if bored_names:
        lines.append(
            "最近有点玩腻/做腻：" + "、".join(bored_names)
        )

    lines.append(
        "这些偏好来自真实生活/游戏经历，会慢慢变化；"
        "不要因为一次输赢就说成永久最爱或永久讨厌。"
    )

    return "\n".join(lines)
