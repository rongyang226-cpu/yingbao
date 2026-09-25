import random
from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH

TOKYO_TZ = ZoneInfo("Asia/Tokyo")

PLACES = {
    "living_room": ("客厅", "home", "大落地窗、沙发和低矮茶几，是最常待的公共空间。"),
    "kitchen": ("开放式厨房", "home", "和客厅相连，冰箱、料理台和小餐桌都固定存在。"),
    "study": ("书房", "home", "书桌、书架和安静阅读区。"),
    "bedroom": ("主卧", "home", "软床、床边灯和步入式衣帽间。"),
    "bathroom": ("浴室", "home", "干湿分离，有浴缸和独立洗漱台。"),
    "balcony": ("景观阳台", "home", "能看到东京城市天际线和夜景。"),
    "game_room": ("独立游戏房", "home", "多屏电脑、主机、掌机和收藏展示柜。"),
    "building_lobby": ("公寓大堂", "building", "出入住宅楼时经过的安静公共区域。"),
    "nearby_store": ("附近便利店", "neighborhood", "步行生活圈里的便利店，可以买饮料和日用品。"),
    "nearby_cafe": ("附近咖啡店", "neighborhood", "适合坐一会儿、看东西或发呆。"),
    "nearby_bookstore": ("附近书店", "neighborhood", "生活圈里固定存在的小书店。"),
    "neighborhood_park": ("附近公园", "neighborhood", "天气合适时可以散步或坐一会儿。"),
    "nearby_station": ("附近车站", "neighborhood", "连接东京其他区域的交通节点。"),
    "riverside_walk": ("河边散步道", "neighborhood", "天气舒服时适合慢慢走一段。"),
}


def now():
    return datetime.now(TOKYO_TZ).isoformat()


def place_name(key: str) -> str:
    return PLACES.get(key, (key or "未知地点", "", ""))[0]


async def init_world_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS world_presence (
            id INTEGER PRIMARY KEY CHECK(id=1),
            place_key TEXT NOT NULL,
            arrived_at TEXT NOT NULL,
            reason TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS world_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            from_place TEXT,
            to_place TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_world_events_time
        ON world_events(created_at);
        """)

        t = now()
        await db.execute(
            """
            INSERT OR IGNORE INTO world_presence
            (id, place_key, arrived_at, reason, updated_at)
            VALUES (1, 'living_room', ?, 'initial', ?)
            """,
            (t, t),
        )
        await db.commit()


async def get_presence():
    await init_world_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT place_key, arrived_at, reason, updated_at
            FROM world_presence
            WHERE id=1
            """
        )
        row = await cur.fetchone()

    key = row[0]
    name, kind, description = PLACES.get(
        key,
        (key, "unknown", "未定义地点"),
    )

    return {
        "place_key": key,
        "place_name": name,
        "kind": kind,
        "description": description,
        "arrived_at": row[1],
        "reason": row[2],
        "updated_at": row[3],
    }


async def set_presence(place_key: str, *, reason=None):
    await init_world_db()

    if place_key not in PLACES:
        raise ValueError(f"unknown world place: {place_key}")

    current = await get_presence()

    if current["place_key"] == place_key:
        return {
            **current,
            "changed": False,
            "from_place": current["place_key"],
        }

    t = now()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE world_presence
            SET place_key=?, arrived_at=?, reason=?, updated_at=?
            WHERE id=1
            """,
            (place_key, t, reason, t),
        )
        await db.execute(
            """
            INSERT INTO world_events
            (event_type, from_place, to_place, reason, created_at)
            VALUES ('move', ?, ?, ?, ?)
            """,
            (
                current["place_key"],
                place_key,
                reason,
                t,
            ),
        )
        await db.commit()

    result = await get_presence()
    result["changed"] = True
    result["from_place"] = current["place_key"]
    return result


def _weather_allows_outing(weather):
    if not weather:
        return True

    try:
        precipitation = float(weather.get("precipitation") or 0)
    except Exception:
        precipitation = 0.0

    code = weather.get("weather_code")
    try:
        code = int(code)
    except Exception:
        code = -1

    # 大雨/雷暴/明显降水时尽量待在家。
    if precipitation >= 1.5:
        return False
    if code in {65, 67, 75, 82, 86, 95, 96, 99}:
        return False

    return True


def choose_place_for_activity(
    activity,
    *,
    weather=None,
    hour=None,
):
    hour = datetime.now(TOKYO_TZ).hour if hour is None else int(hour)

    mandatory = {
        "sleeping": "bedroom",
        "preparing_sleep": "bedroom",
        "washing": "bathroom",
        "gaming": "game_room",
        "organizing": "study",
        "coffee": "nearby_cafe",
        "shopping": "nearby_store",
    }
    if activity in mandatory:
        return mandatory[activity]

    can_out = (
        8 <= hour <= 21
        and _weather_allows_outing(weather)
    )

    pools = {
        "walking": [
            ("neighborhood_park", 45 if can_out else 0),
            ("riverside_walk", 35 if can_out else 0),
            ("nearby_station", 20 if can_out else 0),
        ],
        "reading": [
            ("study", 70),
            ("living_room", 15),
            ("nearby_cafe", 8 if can_out else 0),
            ("nearby_bookstore", 7 if can_out else 0),
        ],
        "eating": [
            ("kitchen", 78),
            ("nearby_cafe", 12 if can_out else 0),
            ("nearby_store", 10 if can_out else 0),
        ],
        "dazing": [
            ("balcony", 45),
            ("living_room", 35),
            ("neighborhood_park", 12 if can_out else 0),
            ("riverside_walk", 8 if can_out else 0),
        ],
        "idle": [
            ("living_room", 58),
            ("balcony", 22),
            ("nearby_store", 8 if can_out else 0),
            ("neighborhood_park", 7 if can_out else 0),
            ("nearby_cafe", 5 if can_out else 0),
        ],
        "phone": [
            ("bedroom", 42),
            ("living_room", 43),
            ("nearby_cafe", 15 if can_out else 0),
        ],
        "resting": [
            ("bedroom", 55),
            ("living_room", 35),
            ("nearby_cafe", 10 if can_out else 0),
        ],
        "listening": [
            ("living_room", 55),
            ("bedroom", 20),
            ("balcony", 15),
            ("riverside_walk", 10 if can_out else 0),
        ],
    }

    options = [
        (place, weight)
        for place, weight in pools.get(activity, [("living_room", 100)])
        if weight > 0
    ]

    if not options:
        options = [("living_room", 100)]

    names = [x[0] for x in options]
    weights = [x[1] for x in options]
    return random.choices(names, weights=weights, k=1)[0]


async def sync_presence_for_activity(
    activity,
    *,
    weather=None,
    allow_move=False,
):
    current = await get_presence()

    # 睡眠、洗漱、游戏等具有强地点约束，无论是否新活动都要同步。
    mandatory = activity in {
        "sleeping",
        "preparing_sleep",
        "washing",
        "gaming",
        "organizing",
        "coffee",
        "shopping",
    }

    if not allow_move and not mandatory:
        return {
            **current,
            "changed": False,
            "from_place": current["place_key"],
        }

    target = choose_place_for_activity(
        activity,
        weather=weather,
    )

    return await set_presence(
        target,
        reason=f"activity:{activity}",
    )


def build_world_catalog_context() -> str:
    now_dt = datetime.now(TOKYO_TZ)
    groups = {
        "住宅内部": [],
        "楼内": [],
        "附近生活圈": [],
    }

    for key, (name, kind, desc) in PLACES.items():
        if kind == "home":
            groups["住宅内部"].append(name)
        elif kind == "building":
            groups["楼内"].append(name)
        else:
            groups["附近生活圈"].append(name)

    return "\n".join([
        f"东京当地时间：{now_dt:%Y-%m-%d %H:%M}",
        "住宅内部：" + "、".join(groups["住宅内部"]),
        "楼内：" + "、".join(groups["楼内"]),
        "附近生活圈：" + "、".join(groups["附近生活圈"]),
        "这些地点属于萤持续存在的虚拟东京生活世界，不是临时编出来的场景。",
        "只有程序明确记录萤当前到达某处时，才能说自己正在那里或刚去过那里。",
        "外部现实信息（天气、时间等）仍必须由真实工具提供。",
    ])



async def get_recent_world_events(limit=8):
    await init_world_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT from_place, to_place, reason, created_at
            FROM world_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = await cur.fetchall()

    result = []

    for from_place, to_place, reason, created_at in reversed(rows):
        result.append({
            "from_place": from_place,
            "from_name": place_name(from_place),
            "to_place": to_place,
            "to_name": place_name(to_place),
            "reason": reason,
            "created_at": created_at,
        })

    return result
