from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH
from app.activity.needs import get_needs, activity_need_bonus
from app.activity.inventory import get_low_stock_items
from app.activity.domestic import get_shopping_list, get_household_state

TOKYO_TZ = ZoneInfo("Asia/Tokyo")

IMPULSE_LIBRARY = [
    ("washing", "等下想去洗个澡，清醒一下", 0.85),
    ("reading", "突然有点想安静看会儿东西", 0.70),
    ("gaming", "等会儿想玩一小会儿游戏", 0.75),
    ("organizing", "看着有点乱，想顺手收拾一下", 0.60),
    ("walking", "有点想出去走一圈", 0.55),
    ("coffee", "想去附近坐一会儿，换换空气", 0.45),
    ("shopping", "好像该顺路补点日用品了", 0.42),
    ("eating", "有点想找点东西吃", 0.58),
    ("resting", "等下想窝一会儿，什么都不干", 0.65),
]


def now_tokyo():
    return datetime.now(TOKYO_TZ)


async def init_impulse_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS spontaneous_impulses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity TEXT NOT NULL,
            thought TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            strength REAL NOT NULL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            not_before TEXT,
            expires_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            deferred_count INTEGER NOT NULL DEFAULT 0,
            final_reason TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_spontaneous_impulses_status
        ON spontaneous_impulses(status, created_at);
        """)
        await db.commit()


async def maintain_impulses(*, life, weather=None):
    await init_impulse_db()
    now = now_tokyo()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE spontaneous_impulses
            SET status='expired',
                final_reason='expired_naturally'
            WHERE status='pending'
              AND expires_at IS NOT NULL
              AND expires_at < ?
            """,
            (now.isoformat(),),
        )

        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM spontaneous_impulses
            WHERE status IN ('pending', 'active')
            """
        )
        active_count = int((await cur.fetchone())[0])

        # 睡觉时不会凭空冒出新念头。
        if life.get("sleep_state") == "sleeping":
            await db.commit()
            return None

        # 最多同时挂三个小念头，避免像任务清单。
        if active_count >= 3:
            await db.commit()
            return None

        # 每五分钟约 3.5% 概率产生一个念头，保持稀疏。
        if random.random() >= 0.035:
            await db.commit()
            return None

        choices = list(IMPULSE_LIBRARY)
        hour = now.hour
        energy = float(life.get("energy") or 0.5)

        # 依据当前状态做很轻的筛选，不写死行为。
        if hour < 8 or hour >= 22:
            choices = [x for x in choices if x[0] not in {"walking", "coffee", "shopping"}]
        if energy < 0.30:
            choices = [x for x in choices if x[0] not in {"walking", "shopping", "gaming"}]

        if not choices:
            await db.commit()
            return None

        # 家里库存偏少时，补货念头会更容易冒出来。
        try:
            low_stock = await get_low_stock_items()
        except Exception:
            low_stock = []

        if low_stock:
            choices.append(
                (
                    "shopping",
                    "家里有些东西快不够了，想顺路补一点",
                    1.25,
                )
            )

        activities = [x[0] for x in choices]
        try:
            needs = await get_needs()
        except Exception:
            needs = {}

        weights = []
        for item in choices:
            activity_name, _thought, base_weight = item
            need_bonus = activity_need_bonus(
                activity_name,
                needs,
            )
            weights.append(
                max(0.05, base_weight * (1.0 + need_bonus))
            )

        activity = random.choices(
            activities,
            weights=weights,
            k=1,
        )[0]
        thought = next(x[1] for x in choices if x[0] == activity)

        # 刚冒出的念头通常不会立刻执行。
        not_before = now + timedelta(minutes=random.randint(10, 45))
        expires_at = now + timedelta(minutes=random.randint(120, 360))
        strength = round(random.uniform(0.35, 0.82), 3)

        cur = await db.execute(
            """
            INSERT INTO spontaneous_impulses
            (activity, thought, status, strength, created_at, not_before, expires_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                activity,
                thought,
                strength,
                now.isoformat(),
                not_before.isoformat(),
                expires_at.isoformat(),
            ),
        )
        await db.commit()
        return {
            "id": cur.lastrowid,
            "activity": activity,
            "thought": thought,
            "strength": strength,
        }


async def get_actionable_impulse():
    await init_impulse_db()
    now = now_tokyo().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, activity, thought, strength, created_at,
                   not_before, expires_at, deferred_count
            FROM spontaneous_impulses
            WHERE status='pending'
              AND (not_before IS NULL OR not_before <= ?)
              AND (expires_at IS NULL OR expires_at >= ?)
            ORDER BY strength DESC, created_at ASC
            LIMIT 1
            """,
            (now, now),
        )
        row = await cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "activity": row[1],
        "thought": row[2],
        "strength": row[3],
        "created_at": row[4],
        "not_before": row[5],
        "expires_at": row[6],
        "deferred_count": row[7],
    }


async def mark_impulse_started(activity):
    await init_impulse_db()
    now = now_tokyo().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id
            FROM spontaneous_impulses
            WHERE status='pending'
              AND activity=?
              AND (not_before IS NULL OR not_before <= ?)
            ORDER BY strength DESC, created_at ASC
            LIMIT 1
            """,
            (activity, now),
        )
        row = await cur.fetchone()
        if not row:
            return False

        await db.execute(
            """
            UPDATE spontaneous_impulses
            SET status='active',
                started_at=?
            WHERE id=?
            """,
            (now, row[0]),
        )
        await db.commit()
        return True


async def complete_active_impulse(activity, *, reason="activity_finished"):
    await init_impulse_db()
    now = now_tokyo().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE spontaneous_impulses
            SET status='completed',
                completed_at=?,
                final_reason=?
            WHERE status='active'
              AND activity=?
            """,
            (now, reason, activity),
        )
        await db.commit()
        return cur.rowcount > 0


async def defer_impulse(impulse_id, *, minutes=None, reason="not_now"):
    await init_impulse_db()
    now = now_tokyo()
    minutes = int(minutes or random.randint(20, 60))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE spontaneous_impulses
            SET not_before=?,
                deferred_count=deferred_count+1,
                final_reason=?
            WHERE id=? AND status='pending'
            """,
            (
                (now + timedelta(minutes=minutes)).isoformat(),
                reason,
                int(impulse_id),
            ),
        )
        await db.commit()


async def get_recent_impulses(limit=5):
    await init_impulse_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, activity, thought, status, strength,
                   created_at, not_before, expires_at,
                   started_at, completed_at, deferred_count, final_reason
            FROM spontaneous_impulses
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = await cur.fetchall()

    keys = [
        "id", "activity", "thought", "status", "strength",
        "created_at", "not_before", "expires_at",
        "started_at", "completed_at", "deferred_count", "final_reason",
    ]
    return [dict(zip(keys, row)) for row in rows]


def render_impulses(items):
    if not items:
        return "现在脑子里没有特别挂着的小念头。"

    visible = [
        x for x in items
        if x.get("status") in {"pending", "active"}
    ]
    if not visible:
        return "现在没有还挂着、等着去做的小念头。"

    lines = []
    for item in visible[:3]:
        state = "已经开始做" if item["status"] == "active" else "还只是想想"
        deferred = int(item.get("deferred_count") or 0)
        suffix = f"，已经往后拖过{deferred}次" if deferred else ""
        lines.append(
            f"- {item['thought']}（{state}{suffix}）"
        )

    return "\n".join(lines)
