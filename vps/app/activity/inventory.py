from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH

TOKYO_TZ = ZoneInfo("Asia/Tokyo")

DEFAULT_ITEMS = {
    "ready_food": {"name": "即食食物", "qty": 6.0, "unit": "份", "min": 2.0, "target": 8.0},
    "drinks": {"name": "饮料", "qty": 8.0, "unit": "瓶", "min": 3.0, "target": 10.0},
    "bath_supplies": {"name": "洗浴用品", "qty": 12.0, "unit": "次", "min": 4.0, "target": 15.0},
    "daily_goods": {"name": "日用品", "qty": 8.0, "unit": "份", "min": 3.0, "target": 10.0},
}


def now_tokyo():
    return datetime.now(TOKYO_TZ)


async def init_inventory_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS household_inventory (
            item_key TEXT PRIMARY KEY,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            min_quantity REAL NOT NULL,
            target_quantity REAL NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            delta REAL NOT NULL,
            quantity_after REAL NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
        );
        """)

        t = now_tokyo().isoformat()
        for key, item in DEFAULT_ITEMS.items():
            await db.execute(
                """
                INSERT OR IGNORE INTO household_inventory
                (item_key, item_name, quantity, unit, min_quantity, target_quantity, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key, item["name"], item["qty"], item["unit"],
                    item["min"], item["target"], t,
                ),
            )
        await db.commit()


async def get_inventory():
    await init_inventory_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT item_key, item_name, quantity, unit,
                   min_quantity, target_quantity, updated_at
            FROM household_inventory
            ORDER BY item_key
            """
        )
        rows = await cur.fetchall()

    return {
        row[0]: {
            "item_key": row[0],
            "item_name": row[1],
            "quantity": row[2],
            "unit": row[3],
            "min_quantity": row[4],
            "target_quantity": row[5],
            "updated_at": row[6],
        }
        for row in rows
    }


async def change_item(item_key, delta, *, reason=None, event_type="adjust"):
    await init_inventory_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT quantity
            FROM household_inventory
            WHERE item_key=?
            """,
            (item_key,),
        )
        row = await cur.fetchone()
        if not row:
            raise KeyError(item_key)

        new_qty = max(0.0, float(row[0]) + float(delta))
        t = now_tokyo().isoformat()

        await db.execute(
            """
            UPDATE household_inventory
            SET quantity=?, updated_at=?
            WHERE item_key=?
            """,
            (new_qty, t, item_key),
        )
        await db.execute(
            """
            INSERT INTO inventory_events
            (event_type, item_key, delta, quantity_after, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, item_key, float(delta), new_qty, reason, t),
        )
        await db.commit()

    return new_qty


async def consume_for_activity(activity):
    inventory = await get_inventory()

    if activity == "eating":
        if inventory["ready_food"]["quantity"] < 1.0:
            return {"ok": False, "reason": "no_food"}
        await change_item(
            "ready_food", -1.0,
            reason="activity:eating",
            event_type="consume",
        )
        return {"ok": True, "consumed": {"ready_food": 1.0}}

    if activity == "washing":
        if inventory["bath_supplies"]["quantity"] < 1.0:
            return {"ok": False, "reason": "no_bath_supplies"}
        await change_item(
            "bath_supplies", -1.0,
            reason="activity:washing",
            event_type="consume",
        )
        return {"ok": True, "consumed": {"bath_supplies": 1.0}}

    return {"ok": True, "consumed": {}}


async def restock_after_shopping():
    inventory = await get_inventory()
    added = {}

    for key, item in inventory.items():
        if key in {"ready_food", "drinks"}:
            continue
        qty = float(item["quantity"])
        target = float(item["target_quantity"])
        if qty >= target:
            continue

        delta = target - qty
        await change_item(
            key,
            delta,
            reason="activity:shopping",
            event_type="restock",
        )
        added[key] = delta

    return added


async def get_low_stock_items():
    inventory = await get_inventory()
    low = []
    for item in inventory.values():
        if item.get("item_key") in {"ready_food", "drinks"}:
            continue
        if float(item["quantity"]) <= float(item["min_quantity"]):
            low.append(item)
    return low


def render_inventory(inventory):
    lines = []
    for key in ("bath_supplies", "daily_goods"):
        item = inventory[key]
        qty = float(item["quantity"])
        low = qty <= float(item["min_quantity"])
        state = "偏少" if low else "够用"
        lines.append(
            f"{item['item_name']}：{qty:g}{item['unit']}（{state}）"
        )
    return "；".join(lines)
