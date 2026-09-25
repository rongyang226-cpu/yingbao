from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH
from app.activity.inventory import (
    init_inventory_db,
    get_inventory,
    change_item,
    restock_after_shopping,
)
from app.activity.home_world import (
    get_home_world,
    update_home_world,
)

TOKYO_TZ = ZoneInfo("Asia/Tokyo")

PANTRY_DEFAULTS = {
    "instant_noodles": ("泡面", "meal", 2.0, "份", 2.0, 4.0, 120, 0.56),
    "onigiri": ("饭团", "meal", 2.0, "个", 1.0, 3.0, 2, 0.64),
    "frozen_dumplings": ("速冻饺子", "meal", 3.0, "份", 1.0, 4.0, 45, 0.61),
    "eggs": ("鸡蛋", "meal", 3.0, "份", 1.0, 4.0, 12, 0.67),
    "toast": ("吐司", "meal", 3.0, "份", 1.0, 4.0, 5, 0.54),
    "yogurt": ("酸奶", "snack", 2.0, "杯", 1.0, 3.0, 10, 0.62),
    "fruit": ("水果", "snack", 3.0, "份", 1.0, 4.0, 6, 0.66),
    "frozen_fried_rice": ("速冻炒饭", "meal", 2.0, "份", 1.0, 3.0, 45, 0.63),
    "sandwich": ("三明治", "meal", 1.0, "份", 1.0, 2.0, 3, 0.60),
    "pudding": ("布丁", "snack", 2.0, "个", 1.0, 3.0, 8, 0.58),
    "water": ("矿泉水", "drink", 4.0, "瓶", 2.0, 6.0, 180, 0.55),
    "tea": ("无糖茶", "drink", 2.0, "瓶", 1.0, 3.0, 120, 0.64),
    "milk": ("牛奶", "drink", 2.0, "盒", 1.0, 3.0, 8, 0.61),
}

FOOD_PREPARATION = {
    "instant_noodles": "泡了泡面",
    "onigiri": "拿了饭团",
    "frozen_dumplings": "煮了速冻饺子",
    "eggs": "煎了鸡蛋",
    "toast": "烤了吐司",
    "yogurt": "拿了酸奶",
    "fruit": "洗了水果",
    "frozen_fried_rice": "热了速冻炒饭",
    "sandwich": "拿了三明治",
    "pudding": "拿了布丁",
}

OUTFIT_PRESETS = {
    "home_warm": "白色oversized短袖、浅蓝短裤、白拖鞋",
    "home_cool": "宽松长袖上衣、居家长裤、白色室内拖鞋",
    "outside_warm": "白色宽松短袖、浅蓝短裤、轻便运动鞋",
    "outside_mild": "薄外套、白色上衣、浅色长裤、运动鞋",
    "outside_cool": "保暖外套、长袖上衣、长裤、运动鞋",
    "rain": "轻便防水外套、长裤、防滑运动鞋",
    "sleep": "宽松睡衣",
}


WARDROBE_DEFAULTS = {
    "home_white_tee": ("白色oversized短袖+浅蓝短裤", "home", "clean_soft", 0.20, 1, 0, 0, 0.72),
    "home_knit": ("奶白薄针织上衣+浅灰居家长裤", "home", "soft", 0.48, 1, 0, 0, 0.66),
    "white_dress": ("白色轻盈连衣小裙子", "dress", "moonlight", 0.28, 1, 1, 0, 0.78),
    "moonlight_lace_dress": ("月白冰蓝薄纱蕾丝礼裙+浅蓝细腰带+半透明披袖+白花发饰", "dress", "moonlight_ethereal", 0.30, 1, 1, 0, 0.84),
    "blue_pleated_skirt": ("浅蓝百褶短裙+白色轻薄上衣", "dress", "cute_clean", 0.24, 1, 1, 0, 0.75),
    "cream_knit_dress": ("奶白针织连衣裙", "dress", "soft_elegant", 0.58, 1, 1, 0, 0.71),
    "black_simple_dress": ("黑色简约连衣裙", "dress", "quiet_elegant", 0.42, 1, 1, 0, 0.69),
    "floral_dress": ("低饱和碎花连衣裙", "dress", "gentle", 0.30, 1, 1, 0, 0.64),
    "outside_light": ("白色上衣+浅色长裤+小白鞋", "outside", "clean", 0.32, 0, 1, 0, 0.67),
    "outside_mild": ("薄外套+白色上衣+浅色长裤+运动鞋", "outside", "casual", 0.55, 0, 1, 0, 0.63),
    "outside_cold": ("保暖外套+长袖上衣+长裤+运动鞋", "outside", "warm", 0.85, 0, 1, 0, 0.58),
    "rain_set": ("轻便防水外套+长裤+防滑运动鞋", "outside", "rain", 0.52, 0, 1, 1, 0.55),
    "sleep_pajamas": ("奶白色宽松睡衣", "sleep", "soft", 0.42, 1, 0, 0, 0.72),
    "sleep_dress": ("浅色薄款睡裙", "sleep", "light", 0.20, 1, 0, 0, 0.68),
}


def now_tokyo():
    return datetime.now(TOKYO_TZ)


def clamp(v):
    return max(0.0, min(1.0, float(v)))


async def init_domestic_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS pantry_items (
            item_key TEXT PRIMARY KEY,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            min_quantity REAL NOT NULL,
            target_quantity REAL NOT NULL,
            shelf_life_days INTEGER NOT NULL,
            expires_at TEXT,
            preference REAL NOT NULL DEFAULT 0.5,
            fatigue REAL NOT NULL DEFAULT 0.0,
            last_eaten_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            satisfaction REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS household_state (
            id INTEGER PRIMARY KEY CHECK(id=1),
            dishes REAL NOT NULL DEFAULT 0.10,
            laundry REAL NOT NULL DEFAULT 0.15,
            trash REAL NOT NULL DEFAULT 0.10,
            clutter REAL NOT NULL DEFAULT 0.18,
            thirst REAL NOT NULL DEFAULT 0.22,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wardrobe_state (
            id INTEGER PRIMARY KEY CHECK(id=1),
            outfit_key TEXT NOT NULL,
            outfit_desc TEXT NOT NULL,
            reason TEXT,
            changed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wardrobe_items (
            item_key TEXT PRIMARY KEY,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            style TEXT,
            warmth REAL NOT NULL DEFAULT 0.5,
            indoor_ok INTEGER NOT NULL DEFAULT 1,
            outdoor_ok INTEGER NOT NULL DEFAULT 1,
            rain_ok INTEGER NOT NULL DEFAULT 0,
            owned INTEGER NOT NULL DEFAULT 1,
            preference REAL NOT NULL DEFAULT 0.6,
            fatigue REAL NOT NULL DEFAULT 0.0,
            last_worn_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS domestic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            subject TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS domestic_daily_usage (
            local_date TEXT PRIMARY KEY,
            daily_goods_used INTEGER NOT NULL DEFAULT 0
        );
        """)

        now = now_tokyo()
        for key, data in PANTRY_DEFAULTS.items():
            name, category, qty, unit, min_q, target_q, days, pref = data
            expires_at = (now + timedelta(days=days)).isoformat()
            await db.execute(
                """
                INSERT OR IGNORE INTO pantry_items
                (item_key, item_name, category, quantity, unit,
                 min_quantity, target_quantity, shelf_life_days,
                 expires_at, preference, fatigue, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?)
                """,
                (
                    key, name, category, qty, unit,
                    min_q, target_q, days, expires_at,
                    pref, now.isoformat(),
                ),
            )

        for key, data in WARDROBE_DEFAULTS.items():
            name, category, style, warmth, indoor_ok, outdoor_ok, rain_ok, pref = data
            await db.execute(
                """
                INSERT OR IGNORE INTO wardrobe_items
                (item_key, item_name, category, style, warmth,
                 indoor_ok, outdoor_ok, rain_ok, owned,
                 preference, fatigue, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 0.0, ?)
                """,
                (
                    key, name, category, style, warmth,
                    indoor_ok, outdoor_ok, rain_ok,
                    pref, now.isoformat(),
                ),
            )

        await db.execute(
            """
            INSERT OR IGNORE INTO household_state
            (id, updated_at)
            VALUES (1, ?)
            """,
            (now.isoformat(),),
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO wardrobe_state
            (id, outfit_key, outfit_desc, reason, changed_at)
            VALUES (1, 'home_warm', ?, 'initial', ?)
            """,
            (OUTFIT_PRESETS["home_warm"], now.isoformat()),
        )
        await db.commit()


async def _event(event_type, subject=None, detail=None):
    await init_domestic_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO domestic_events
            (event_type, subject, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, subject, detail, now_tokyo().isoformat()),
        )
        await db.commit()


async def get_pantry():
    await init_domestic_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT item_key, item_name, category, quantity, unit,
                   min_quantity, target_quantity, shelf_life_days,
                   expires_at, preference, fatigue, last_eaten_at
            FROM pantry_items
            ORDER BY category, item_name
            """
        )
        rows = await cur.fetchall()

    keys = [
        "item_key", "item_name", "category", "quantity", "unit",
        "min_quantity", "target_quantity", "shelf_life_days",
        "expires_at", "preference", "fatigue", "last_eaten_at",
    ]
    return [dict(zip(keys, row)) for row in rows]


async def expire_food():
    await init_domestic_db()
    now = now_tokyo()
    expired = []
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT item_key, item_name, quantity, expires_at
            FROM pantry_items
            WHERE quantity > 0 AND expires_at IS NOT NULL
            """
        )
        for key, name, qty, expires_at in await cur.fetchall():
            try:
                dt = datetime.fromisoformat(expires_at)
            except Exception:
                continue
            if dt <= now:
                await db.execute(
                    """
                    UPDATE pantry_items
                    SET quantity=0, updated_at=?
                    WHERE item_key=?
                    """,
                    (now.isoformat(), key),
                )
                expired.append((key, name, qty))
        await db.commit()

    if expired:
        state = await get_household_state()
        await set_household_state(
            trash=state["trash"] + min(
                0.30,
                0.05 * len(expired),
            )
        )

    for key, name, qty in expired:
        await _event("food_expired", key, f"{name}过期，丢弃{qty:g}")
    return expired


async def get_household_state():
    await init_domestic_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT dishes, laundry, trash, clutter, thirst, updated_at
            FROM household_state WHERE id=1
            """
        )
        row = await cur.fetchone()
    return {
        "dishes": row[0],
        "laundry": row[1],
        "trash": row[2],
        "clutter": row[3],
        "thirst": row[4],
        "updated_at": row[5],
    }


async def set_household_state(**changes):
    current = await get_household_state()
    for key in ("dishes", "laundry", "trash", "clutter", "thirst"):
        if key in changes and changes[key] is not None:
            current[key] = clamp(changes[key])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE household_state
            SET dishes=?, laundry=?, trash=?, clutter=?, thirst=?, updated_at=?
            WHERE id=1
            """,
            (
                current["dishes"], current["laundry"], current["trash"],
                current["clutter"], current["thirst"], now_tokyo().isoformat(),
            ),
        )
        await db.commit()
    return await get_household_state()


async def consume_daily_goods_once():
    await init_domestic_db()
    today = now_tokyo().date().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO domestic_daily_usage
            (local_date, daily_goods_used)
            VALUES (?, 0)
            """,
            (today,),
        )
        cur = await db.execute(
            """
            SELECT daily_goods_used
            FROM domestic_daily_usage
            WHERE local_date=?
            """,
            (today,),
        )
        used = int((await cur.fetchone())[0] or 0)
        if used:
            await db.commit()
            return False

        await db.execute(
            """
            UPDATE domestic_daily_usage
            SET daily_goods_used=1
            WHERE local_date=?
            """,
            (today,),
        )
        await db.commit()

    try:
        inv = await get_inventory()
        if float(inv["daily_goods"]["quantity"]) > 0:
            await change_item(
                "daily_goods",
                -1.0,
                reason="daily_household_use",
                event_type="consume",
            )
            await _event(
                "daily_use",
                "daily_goods",
                "今天消耗了一份日用品",
            )
    except Exception:
        pass
    return True


async def evolve_domestic(*, life):
    await expire_food()

    # “吃腻”会随着现实时间慢慢淡下来，而不是永久挂着。
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                UPDATE pantry_items
                SET fatigue=MAX(0.0, fatigue-0.0012)
                """
            )
            await db.commit()
    except Exception:
        pass

    state = await get_household_state()
    sleeping = life.get("sleep_state") == "sleeping"
    activity = life.get("activity")

    if not sleeping:
        await consume_daily_goods_once()

    dishes = state["dishes"] + (0.0002 if sleeping else 0.0007)
    laundry = state["laundry"] + (0.0004 if sleeping else 0.0010)
    trash = state["trash"] + (0.0002 if sleeping else 0.0006)
    clutter = state["clutter"] + (0.0002 if sleeping else 0.0008)
    thirst = state["thirst"] + (0.0012 if sleeping else 0.0030)

    if activity == "organizing":
        clutter -= 0.006
    if activity == "eating":
        dishes += 0.004
        trash += 0.002
        thirst += 0.002

    # A small autonomous drink is a real recorded micro-action.
    if not sleeping and thirst >= 0.72:
        try:
            drink = await choose_and_consume_drink()
            if drink.get("ok"):
                thirst -= 0.48
        except Exception:
            pass

    result = await set_household_state(
        dishes=dishes,
        laundry=laundry,
        trash=trash,
        clutter=clutter,
        thirst=thirst,
    )

    pressure = max(
        float(result["dishes"]),
        float(result["trash"]),
        float(result["clutter"]),
    )
    if pressure >= 0.78:
        cleanliness_label = "有些凌乱，需要认真收拾"
    elif pressure >= 0.52:
        cleanliness_label = "基本整洁，但有些地方开始乱了"
    else:
        cleanliness_label = "整洁"

    try:
        world = await get_home_world()
        if world.get("room_cleanliness") != cleanliness_label:
            await update_home_world(
                room_cleanliness=cleanliness_label
            )
    except Exception:
        pass

    return result


async def choose_and_consume_drink():
    await expire_food()
    pantry = [
        x for x in await get_pantry()
        if x["category"] == "drink"
        and float(x["quantity"]) >= 1
    ]
    if not pantry:
        return {"ok": False, "reason": "no_drinks"}

    weights = []
    for item in pantry:
        pref = float(item["preference"])
        fatigue = float(item["fatigue"])
        weights.append(
            max(
                0.05,
                (0.35 + pref)
                * (1.0 - 0.70 * fatigue),
            )
        )

    chosen = random.choices(
        pantry,
        weights=weights,
        k=1,
    )[0]

    now = now_tokyo()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE pantry_items
            SET quantity=MAX(0, quantity-1),
                fatigue=MIN(1.0, fatigue+0.10),
                last_eaten_at=?,
                updated_at=?
            WHERE item_key=?
            """,
            (
                now.isoformat(),
                now.isoformat(),
                chosen["item_key"],
            ),
        )
        await db.execute(
            """
            UPDATE pantry_items
            SET fatigue=MAX(0.0, fatigue-0.012)
            WHERE category='drink'
              AND item_key<>?
            """,
            (chosen["item_key"],),
        )
        await db.commit()

    await _event(
        "drink",
        chosen["item_key"],
        f"口渴时喝了{chosen['item_name']}",
    )
    return {
        "ok": True,
        "item_key": chosen["item_key"],
        "item_name": chosen["item_name"],
    }


async def choose_and_consume_meal(hunger=None):
    await expire_food()
    pantry = [x for x in await get_pantry() if float(x["quantity"]) >= 1]
    if not pantry:
        return {"ok": False, "reason": "pantry_empty"}

    candidates = [x for x in pantry if x["category"] in {"meal", "snack"}]
    if not candidates:
        return {"ok": False, "reason": "no_edible_food"}

    weights = []
    for item in candidates:
        pref = float(item["preference"])
        fatigue = float(item["fatigue"])

        if hunger is not None and float(hunger) >= 0.68:
            meal_bonus = 1.55 if item["category"] == "meal" else 0.48
        elif hunger is not None and float(hunger) <= 0.42:
            meal_bonus = 0.88 if item["category"] == "meal" else 1.05
        else:
            meal_bonus = 1.25 if item["category"] == "meal" else 0.72

        weights.append(
            max(
                0.05,
                (0.35 + pref)
                * (1.0 - 0.75 * fatigue)
                * meal_bonus,
            )
        )

    chosen = random.choices(candidates, weights=weights, k=1)[0]
    satisfaction = clamp(
        0.42
        + float(chosen["preference"]) * 0.45
        - float(chosen["fatigue"]) * 0.30
        + random.uniform(-0.08, 0.08)
    )

    now = now_tokyo()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE pantry_items
            SET quantity=MAX(0, quantity-1),
                fatigue=MIN(1.0, fatigue+0.14),
                preference=MIN(1.0, MAX(0.0, preference + ?)),
                last_eaten_at=?,
                updated_at=?
            WHERE item_key=?
            """,
            (
                (satisfaction - 0.55) * 0.018,
                now.isoformat(), now.isoformat(), chosen["item_key"],
            ),
        )
        await db.execute(
            """
            UPDATE pantry_items
            SET fatigue=MAX(0.0, fatigue-0.018)
            WHERE item_key<>?
            """,
            (chosen["item_key"],),
        )
        await db.execute(
            """
            INSERT INTO meal_history
            (item_key, item_name, quantity, satisfaction, created_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (
                chosen["item_key"], chosen["item_name"],
                satisfaction, now.isoformat(),
            ),
        )
        await db.commit()

    state = await get_household_state()
    await set_household_state(
        dishes=state["dishes"] + 0.10,
        trash=state["trash"] + 0.04,
        thirst=state["thirst"] + 0.05,
    )
    preparation = FOOD_PREPARATION.get(
        chosen["item_key"],
        f"准备了{chosen['item_name']}",
    )
    await _event(
        "meal",
        chosen["item_key"],
        f"{preparation}，吃了{chosen['item_name']}，满意度{satisfaction:.2f}",
    )
    await sync_ready_food_count()

    return {
        "ok": True,
        "item_key": chosen["item_key"],
        "item_name": chosen["item_name"],
        "preparation": preparation,
        "satisfaction": satisfaction,
    }


async def sync_ready_food_count():
    pantry = await get_pantry()
    total = sum(float(x["quantity"]) for x in pantry if x["category"] in {"meal", "snack"})
    inv = await get_inventory()
    current = float(inv["ready_food"]["quantity"])
    delta = total - current
    if abs(delta) > 1e-9:
        await change_item(
            "ready_food", delta,
            reason="sync:pantry",
            event_type="sync",
        )
    return total


async def get_shopping_list():
    await expire_food()
    pantry = await get_pantry()
    generic = await get_inventory()
    items = []

    for x in pantry:
        if float(x["quantity"]) <= float(x["min_quantity"]):
            items.append({
                "kind": "pantry",
                "key": x["item_key"],
                "name": x["item_name"],
                "need": max(0.0, float(x["target_quantity"]) - float(x["quantity"])),
                "unit": x["unit"],
            })

    for key, x in generic.items():
        if key in {"ready_food", "drinks"}:
            continue
        if float(x["quantity"]) <= float(x["min_quantity"]):
            items.append({
                "kind": "generic",
                "key": key,
                "name": x["item_name"],
                "need": max(0.0, float(x["target_quantity"]) - float(x["quantity"])),
                "unit": x["unit"],
            })

    return items


async def perform_shopping():
    await init_domestic_db()
    now = now_tokyo()
    bought = []

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT item_key, item_name, quantity, unit,
                   min_quantity, target_quantity, shelf_life_days
            FROM pantry_items
            """
        )
        rows = await cur.fetchall()

        for key, name, qty, unit, min_q, target_q, days in rows:
            if float(qty) > float(min_q):
                continue

            cur2 = await db.execute(
                "SELECT preference, fatigue FROM pantry_items WHERE item_key=?",
                (key,),
            )
            pref, fatigue = await cur2.fetchone()
            adaptive_target = float(target_q)
            if float(pref) >= 0.68 and float(fatigue) < 0.55:
                adaptive_target += 1.0
            if float(fatigue) >= 0.65:
                adaptive_target = max(
                    float(min_q) + 1.0,
                    adaptive_target - 1.0,
                )

            add = max(0.0, adaptive_target - float(qty))
            if add <= 0:
                continue
            await db.execute(
                """
                UPDATE pantry_items
                SET quantity=?,
                    expires_at=?,
                    updated_at=?
                WHERE item_key=?
                """,
                (
                    adaptive_target,
                    (now + timedelta(days=int(days))).isoformat(),
                    now.isoformat(), key,
                ),
            )
            bought.append((name, add, unit))
        await db.commit()

    generic = await restock_after_shopping()
    for key, add in generic.items():
        if key != "ready_food":
            inv = await get_inventory()
            bought.append((inv[key]["item_name"], add, inv[key]["unit"]))

    await sync_ready_food_count()
    await _event(
        "shopping",
        "household",
        "；".join(f"{n}+{q:g}{u}" for n, q, u in bought) or "没有需要补的东西",
    )
    return bought


async def perform_household_chore():
    state = await get_household_state()
    candidates = {
        "dishes": state["dishes"],
        "laundry": state["laundry"],
        "trash": state["trash"],
        "clutter": state["clutter"],
    }
    key = max(candidates, key=candidates.get)
    value = candidates[key]

    names = {
        "dishes": "洗碗和收拾料理台",
        "laundry": "洗衣服并整理晾晒",
        "trash": "收垃圾并丢掉",
        "clutter": "整理房间和桌面",
    }

    if value < 0.28:
        key = "clutter"
        names[key] = "随手整理了一点房间"

    changes = {key: max(0.04, value - 0.58)}
    result = await set_household_state(**changes)
    await _event("chore", key, names[key])
    return {
        "chore": key,
        "description": names[key],
        "state": result,
    }


def activity_domestic_bonus(activity, household, shopping_list):
    household = household or {}
    shopping_list = shopping_list or []

    if activity == "organizing":
        pressure = max(
            float(household.get("dishes") or 0),
            float(household.get("laundry") or 0),
            float(household.get("trash") or 0),
            float(household.get("clutter") or 0),
        )
        return max(0.0, pressure - 0.35) * 2.4

    if activity == "shopping":
        count = len(shopping_list)
        if count <= 0:
            return 0.0
        return min(1.8, 0.35 + count * 0.28)

    return 0.0


async def get_wardrobe_items():
    await init_domestic_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT item_key, item_name, category, style, warmth,
                   indoor_ok, outdoor_ok, rain_ok, owned,
                   preference, fatigue, last_worn_at
            FROM wardrobe_items
            WHERE owned=1
            ORDER BY category, item_name
            """
        )
        rows = await cur.fetchall()

    keys = [
        "item_key", "item_name", "category", "style", "warmth",
        "indoor_ok", "outdoor_ok", "rain_ok", "owned",
        "preference", "fatigue", "last_worn_at",
    ]
    return [dict(zip(keys, row)) for row in rows]


def _wardrobe_weight(item, *, outside, raining, temp, sleeping):
    rain_factor = 1.0

    if sleeping:
        if item["category"] != "sleep":
            return 0.0
    elif outside:
        if not item["outdoor_ok"]:
            return 0.0
        if raining and not item["rain_ok"]:
            # Dresses are not impossible in rain, just much less likely.
            rain_factor = 0.18 if item["category"] == "dress" else 0.35
        else:
            rain_factor = 1.0
    else:
        if not item["indoor_ok"] or item["category"] == "sleep":
            return 0.0
        rain_factor = 1.0

    warmth = float(item["warmth"])
    if temp is None:
        temp_fit = 0.9
    elif temp <= 10:
        temp_fit = max(0.10, 1.0 - abs(warmth - 0.85) * 1.4)
    elif temp <= 18:
        temp_fit = max(0.12, 1.0 - abs(warmth - 0.62) * 1.3)
    elif temp <= 25:
        temp_fit = max(0.15, 1.0 - abs(warmth - 0.40) * 1.2)
    else:
        temp_fit = max(0.10, 1.0 - abs(warmth - 0.22) * 1.5)

    pref = 0.35 + float(item["preference"])
    fatigue = max(0.12, 1.0 - float(item["fatigue"]) * 0.82)

    # She likes soft dresses, but not every day.
    dress_bonus = 1.18 if item["category"] == "dress" else 1.0
    return max(0.01, pref * fatigue * temp_fit * rain_factor * dress_bonus)


async def choose_wardrobe_item(*, activity, weather=None, sleep_state="awake"):
    await init_domestic_db()
    items = await get_wardrobe_items()
    outside = activity in {"walking", "coffee", "shopping"}
    sleeping = sleep_state == "sleeping"
    condition = ""
    temp = None

    if weather:
        condition = str(
            weather.get("weather")
            or weather.get("condition")
            or ""
        )
        try:
            temp = float(weather.get("temperature"))
        except Exception:
            temp = None

    raining = "雨" in condition or "rain" in condition.lower()

    weighted = []
    for item in items:
        w = _wardrobe_weight(
            item,
            outside=outside,
            raining=raining,
            temp=temp,
            sleeping=sleeping,
        )
        if w > 0:
            weighted.append((item, w))

    if not weighted:
        return None

    choice = random.choices(
        [x[0] for x in weighted],
        weights=[x[1] for x in weighted],
        k=1,
    )[0]
    return choice


def render_wardrobe_items(items):
    if not items:
        return "衣柜里暂时没有可用衣物。"

    dresses = [x["item_name"] for x in items if x["category"] == "dress"]
    sleepwear = [x["item_name"] for x in items if x["category"] == "sleep"]
    everyday = [
        x["item_name"]
        for x in items
        if x["category"] in {"home", "outside"}
    ]

    parts = []
    if dresses:
        parts.append("小裙子：" + "、".join(dresses))
    if everyday:
        parts.append("日常：" + "、".join(everyday))
    if sleepwear:
        parts.append("睡衣：" + "、".join(sleepwear))
    return "；".join(parts)


async def get_wardrobe_state():
    await init_domestic_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT outfit_key, outfit_desc, reason, changed_at
            FROM wardrobe_state WHERE id=1
            """
        )
        row = await cur.fetchone()
    return {
        "outfit_key": row[0],
        "outfit_desc": row[1],
        "reason": row[2],
        "changed_at": row[3],
    }


async def update_outfit(*, activity, weather=None, sleep_state="awake"):
    await init_domestic_db()

    current = await get_wardrobe_state()
    items = await get_wardrobe_items()
    item_by_key = {x["item_key"]: x for x in items}
    current_item = item_by_key.get(current.get("outfit_key"))

    outside = activity in {"walking", "coffee", "shopping"}
    sleeping = sleep_state == "sleeping"
    condition = ""
    temp = None
    if weather:
        condition = str(
            weather.get("weather")
            or weather.get("condition")
            or ""
        )
        try:
            temp = float(weather.get("temperature"))
        except Exception:
            temp = None
    raining = "雨" in condition or "rain" in condition.lower()

    # Keep wearing a still-suitable outfit for a while. This prevents
    # unrealistic outfit roulette on every five-minute life tick.
    current_suitable = False
    if current_item:
        if sleeping:
            current_suitable = current_item["category"] == "sleep"
        elif outside:
            current_suitable = bool(current_item["outdoor_ok"])
            if raining and not current_item["rain_ok"]:
                current_suitable = current_item["category"] == "dress"
        else:
            current_suitable = bool(current_item["indoor_ok"]) and current_item["category"] != "sleep"

    changed_age_hours = 999.0
    try:
        changed_at = datetime.fromisoformat(current.get("changed_at"))
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=TOKYO_TZ)
        changed_age_hours = max(
            0.0,
            (now_tokyo() - changed_at.astimezone(TOKYO_TZ)).total_seconds() / 3600.0,
        )
    except Exception:
        pass

    if current_suitable and changed_age_hours < 4.0:
        return current

    chosen = await choose_wardrobe_item(
        activity=activity,
        weather=weather,
        sleep_state=sleep_state,
    )
    if not chosen:
        return current

    if current["outfit_key"] == chosen["item_key"]:
        return current

    if sleeping:
        reason = "sleeping"
    elif outside:
        reason = "outside_rain" if raining else "outside"
    else:
        reason = "home"

    try:
        house = await get_household_state()
        await set_household_state(
            laundry=house["laundry"] + 0.045,
            clutter=house["clutter"] + 0.008,
        )
    except Exception:
        pass

    now = now_tokyo()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE wardrobe_state
            SET outfit_key=?, outfit_desc=?, reason=?, changed_at=?
            WHERE id=1
            """,
            (
                chosen["item_key"],
                chosen["item_name"],
                reason,
                now.isoformat(),
            ),
        )
        await db.execute(
            """
            UPDATE wardrobe_items
            SET fatigue=MAX(0.0, fatigue-0.012)
            WHERE item_key<>?
            """,
            (chosen["item_key"],),
        )
        await db.execute(
            """
            UPDATE wardrobe_items
            SET fatigue=MIN(1.0, fatigue+0.10),
                last_worn_at=?,
                updated_at=?
            WHERE item_key=?
            """,
            (
                now.isoformat(),
                now.isoformat(),
                chosen["item_key"],
            ),
        )
        await db.commit()

    await _event(
        "outfit",
        chosen["item_key"],
        chosen["item_name"],
    )
    return await get_wardrobe_state()




async def get_recent_domestic_events(limit=8):
    await init_domestic_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT event_type, subject, detail, created_at
            FROM domestic_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = await cur.fetchall()

    return [
        {
            "event_type": row[0],
            "subject": row[1],
            "detail": row[2],
            "created_at": row[3],
        }
        for row in rows
    ]


def render_recent_domestic_events(events):
    if not events:
        return "最近没有新的居家事件记录。"

    names = {
        "meal": "吃东西",
        "shopping": "补货",
        "chore": "做家务",
        "drink": "喝东西",
        "food_expired": "处理过期食物",
        "outfit": "换衣服",
        "daily_use": "日用品消耗",
    }
    lines = []
    for item in events[:6]:
        label = names.get(item["event_type"], item["event_type"])
        detail = item.get("detail") or item.get("subject") or ""
        lines.append(f"- {label}：{detail}")
    return "\n".join(lines)


def render_domestic(pantry, household, shopping, wardrobe):
    pantry_text = "、".join(
        f"{x['item_name']}{float(x['quantity']):g}{x['unit']}"
        for x in pantry
        if float(x["quantity"]) > 0
    ) or "没有可吃的东西"

    chores = []
    if household["dishes"] >= 0.55:
        chores.append("碗和料理台该收拾了")
    if household["laundry"] >= 0.55:
        chores.append("衣服该洗了")
    if household["trash"] >= 0.55:
        chores.append("垃圾该丢了")
    if household["clutter"] >= 0.55:
        chores.append("房间有点乱")
    chore_text = "；".join(chores) if chores else "家务目前没有特别积压"

    shop_text = (
        "、".join(f"{x['name']}×{x['need']:g}{x['unit']}" for x in shopping)
        if shopping else "暂时不用专门补货"
    )

    thirst = household["thirst"]
    thirst_text = "明显口渴" if thirst >= 0.72 else ("有点口渴" if thirst >= 0.5 else "不怎么渴")

    stocked = [
        x for x in pantry
        if float(x["quantity"]) > 0
    ]
    favorite = max(
        stocked,
        key=lambda x: float(x["preference"]),
        default=None,
    )
    tired = max(
        stocked,
        key=lambda x: float(x["fatigue"]),
        default=None,
    )
    taste_text = (
        f"目前更偏爱{favorite['item_name']}"
        if favorite
        else "暂时没有明显食物偏好"
    )
    if tired and float(tired["fatigue"]) >= 0.45:
        taste_text += f"；最近对{tired['item_name']}有点吃腻"

    return (
        f"食物/饮品库存：{pantry_text}。\n"
        f"口味：{taste_text}。\n"
        f"家务：{chore_text}；{thirst_text}。\n"
        f"购物清单：{shop_text}。\n"
        f"当前穿着：{wardrobe['outfit_desc']}。"
    )

async def get_recent_meals(limit=5):
    await init_domestic_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT item_name, satisfaction, created_at
            FROM meal_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = await cur.fetchall()
    return [
        {
            "item_name": row[0],
            "satisfaction": row[1],
            "created_at": row[2],
        }
        for row in rows
    ]


async def audit_domestic_consistency(*, repair=True):
    """
    Verify domestic invariants. pantry_items is the source of truth for food;
    household_inventory.ready_food is only its compatibility mirror.
    """
    await init_domestic_db()
    await init_inventory_db()
    repairs = []

    pantry = await get_pantry()
    edible_total = sum(
        float(x["quantity"])
        for x in pantry
        if x["category"] in {"meal", "snack"}
    )
    inv = await get_inventory()
    mirror = float(inv["ready_food"]["quantity"])

    if abs(edible_total - mirror) > 1e-9:
        if repair:
            await change_item(
                "ready_food",
                edible_total - mirror,
                reason="audit:pantry_source_of_truth",
                event_type="repair",
            )
        repairs.append(
            f"ready_food_mirror:{mirror:g}->{edible_total:g}"
        )

    # Defensive clamps for old/corrupt rows.
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT item_key, quantity, fatigue, preference
            FROM pantry_items
            """
        )
        for key, qty, fatigue, pref in await cur.fetchall():
            fixed_qty = max(0.0, float(qty))
            fixed_fatigue = clamp(fatigue)
            fixed_pref = clamp(pref)
            if (
                fixed_qty != float(qty)
                or fixed_fatigue != float(fatigue)
                or fixed_pref != float(pref)
            ):
                if repair:
                    await db.execute(
                        """
                        UPDATE pantry_items
                        SET quantity=?, fatigue=?, preference=?, updated_at=?
                        WHERE item_key=?
                        """,
                        (
                            fixed_qty, fixed_fatigue, fixed_pref,
                            now_tokyo().isoformat(), key,
                        ),
                    )
                repairs.append(f"pantry_clamp:{key}")

        cur = await db.execute(
            """
            SELECT dishes, laundry, trash, clutter, thirst
            FROM household_state WHERE id=1
            """
        )
        row = await cur.fetchone()
        if row:
            fixed = [clamp(x) for x in row]
            if any(float(a) != b for a, b in zip(row, fixed)):
                if repair:
                    await db.execute(
                        """
                        UPDATE household_state
                        SET dishes=?, laundry=?, trash=?, clutter=?, thirst=?, updated_at=?
                        WHERE id=1
                        """,
                        (*fixed, now_tokyo().isoformat()),
                    )
                repairs.append("household_state_clamped")
        if repair:
            await db.commit()

    return {
        "ok": not repairs,
        "repairs": repairs,
        "edible_total": edible_total,
    }
