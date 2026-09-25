from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH

TOKYO_TZ = ZoneInfo("Asia/Tokyo")


def now_tokyo():
    return datetime.now(TOKYO_TZ)


def clamp(value):
    return max(0.0, min(1.0, float(value)))


async def init_needs_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS life_needs (
                id INTEGER PRIMARY KEY CHECK(id=1),
                hunger REAL NOT NULL DEFAULT 0.25,
                cleanliness REAL NOT NULL DEFAULT 0.85,
                boredom REAL NOT NULL DEFAULT 0.30,
                outing_desire REAL NOT NULL DEFAULT 0.35,
                social_need REAL NOT NULL DEFAULT 0.40,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO life_needs
            (id, updated_at)
            VALUES (1, ?)
            """,
            (now_tokyo().isoformat(),),
        )
        await db.commit()


async def get_needs():
    await init_needs_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT hunger, cleanliness, boredom,
                   outing_desire, social_need, updated_at
            FROM life_needs
            WHERE id=1
            """
        )
        row = await cur.fetchone()

    return {
        "hunger": row[0],
        "cleanliness": row[1],
        "boredom": row[2],
        "outing_desire": row[3],
        "social_need": row[4],
        "updated_at": row[5],
    }


async def set_needs(**changes):
    current = await get_needs()
    data = dict(current)
    for key in (
        "hunger",
        "cleanliness",
        "boredom",
        "outing_desire",
        "social_need",
    ):
        if key in changes and changes[key] is not None:
            data[key] = clamp(changes[key])

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE life_needs
            SET hunger=?,
                cleanliness=?,
                boredom=?,
                outing_desire=?,
                social_need=?,
                updated_at=?
            WHERE id=1
            """,
            (
                data["hunger"],
                data["cleanliness"],
                data["boredom"],
                data["outing_desire"],
                data["social_need"],
                now_tokyo().isoformat(),
            ),
        )
        await db.commit()

    return await get_needs()


async def evolve_needs(*, life):
    needs = await get_needs()
    sleeping = life.get("sleep_state") == "sleeping"
    activity = life.get("activity")

    hunger = needs["hunger"]
    cleanliness = needs["cleanliness"]
    boredom = needs["boredom"]
    outing = needs["outing_desire"]
    social = needs["social_need"]

    # Per 5-minute tick: intentionally slow changes.
    hunger += 0.0012 if sleeping else 0.0024
    cleanliness -= 0.0008 if sleeping else 0.0018

    if sleeping:
        boredom -= 0.0010
        outing -= 0.0010
        social -= 0.0010
    else:
        boredom += 0.0018
        outing += 0.0012
        social += 0.0008

    # Current activity can satisfy a need gradually while it is happening.
    if activity in {"gaming", "reading", "listening", "phone"}:
        boredom -= 0.0035
    if activity in {"walking", "coffee", "shopping"}:
        outing -= 0.0045
        boredom -= 0.0015
    if activity == "eating":
        hunger -= 0.0100
    if activity == "washing":
        cleanliness += 0.0120

    # Life-level social desire nudges, but does not replace, social need.
    social_target = float(life.get("social_desire") or 0.5)
    social += (social_target - social) * 0.006

    return await set_needs(
        hunger=hunger,
        cleanliness=cleanliness,
        boredom=boredom,
        outing_desire=outing,
        social_need=social,
    )


async def satisfy_need_for_completed_activity(activity):
    needs = await get_needs()

    changes = {}
    if activity == "eating":
        changes["hunger"] = needs["hunger"] - 0.55
    elif activity == "washing":
        changes["cleanliness"] = needs["cleanliness"] + 0.65
    elif activity in {"gaming", "reading", "listening"}:
        changes["boredom"] = needs["boredom"] - 0.35
    elif activity == "phone":
        changes["boredom"] = needs["boredom"] - 0.20
        changes["social_need"] = needs["social_need"] - 0.08
    elif activity in {"walking", "coffee", "shopping"}:
        changes["outing_desire"] = needs["outing_desire"] - 0.50
        changes["boredom"] = needs["boredom"] - 0.18

    if not changes:
        return needs

    return await set_needs(**changes)


def activity_need_bonus(activity, needs):
    """
    Small additive score used as a soft preference only.
    Higher means the activity better matches current needs.
    """
    hunger = float(needs.get("hunger") or 0)
    cleanliness = float(needs.get("cleanliness") or 1)
    boredom = float(needs.get("boredom") or 0)
    outing = float(needs.get("outing_desire") or 0)
    social = float(needs.get("social_need") or 0)

    if activity == "eating":
        return max(0.0, hunger - 0.35) * 2.8
    if activity == "washing":
        dirty = 1.0 - cleanliness
        return max(0.0, dirty - 0.30) * 2.5
    if activity in {"gaming", "reading", "listening", "phone"}:
        base = max(0.0, boredom - 0.35) * 1.6
        if activity == "phone":
            base += max(0.0, social - 0.55) * 1.1
        return base
    if activity in {"walking", "coffee", "shopping"}:
        return max(0.0, outing - 0.40) * 1.8
    return 0.0


def render_needs(needs):
    def label(value, *, inverse=False):
        value = float(value)
        if inverse:
            value = 1.0 - value
        if value >= 0.78:
            return "很明显"
        if value >= 0.58:
            return "有点明显"
        if value >= 0.38:
            return "一般"
        return "不明显"

    return (
        f"饥饿感={label(needs.get('hunger', 0))}；"
        f"想清洁/洗漱={label(needs.get('cleanliness', 1), inverse=True)}；"
        f"无聊感={label(needs.get('boredom', 0))}；"
        f"想出门={label(needs.get('outing_desire', 0))}；"
        f"想和人互动={label(needs.get('social_need', 0))}。"
    )
