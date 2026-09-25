import aiosqlite
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import DB_PATH


TOKYO_TZ = ZoneInfo("Asia/Tokyo")
ZHENGZHOU_TZ = ZoneInfo("Asia/Shanghai")


async def init_home_world_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS home_world (
                id INTEGER PRIMARY KEY CHECK (id = 1),

                ying_city TEXT NOT NULL DEFAULT '东京',
                owner_city TEXT NOT NULL DEFAULT '东京',

                room_location TEXT NOT NULL DEFAULT 'desk',
                light_state TEXT NOT NULL DEFAULT 'off',

                current_game TEXT,
                game_started_at TEXT,

                room_style TEXT NOT NULL DEFAULT '简洁',
                room_cleanliness TEXT NOT NULL DEFAULT '整洁',
                window_view TEXT NOT NULL DEFAULT '东京城市窗景',
                wall_color TEXT NOT NULL DEFAULT '暖白色',
                desk_style TEXT NOT NULL DEFAULT '浅木色书桌',
                bed_style TEXT NOT NULL DEFAULT '浅色床铺',

                updated_at TEXT NOT NULL
            )
            """
        )

        cur = await db.execute("PRAGMA table_info(home_world)")
        columns = {row[1] for row in await cur.fetchall()}

        if "room_style" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN room_style TEXT NOT NULL DEFAULT '简洁'"
            )

        if "room_cleanliness" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN room_cleanliness TEXT NOT NULL DEFAULT '整洁'"
            )

        if "window_view" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN window_view TEXT NOT NULL DEFAULT '东京城市窗景'"
            )

        if "wall_color" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN wall_color TEXT NOT NULL DEFAULT '暖白色'"
            )

        if "desk_style" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN desk_style TEXT NOT NULL DEFAULT '浅木色书桌'"
            )

        if "bed_style" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN bed_style TEXT NOT NULL DEFAULT '浅色床铺'"
            )

        if "current_entertainment_mode" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN current_entertainment_mode TEXT"
            )

        if "current_entertainment_detail" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN current_entertainment_detail TEXT"
            )

        if "current_entertainment_session" not in columns:
            await db.execute(
                "ALTER TABLE home_world ADD COLUMN current_entertainment_session TEXT"
            )

        # 兼容早期版本遗留的 room_location='bed'。
        await db.execute(
            "UPDATE home_world SET room_location='bedroom' WHERE room_location='bed'"
        )

        await db.execute(
            """
            INSERT OR IGNORE INTO home_world (
                id,
                updated_at
            )
            VALUES (1, ?)
            """,
            (datetime.now(TOKYO_TZ).isoformat(),)
        )

        await db.commit()


async def get_home_world():
    await init_home_world_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                ying_city,
                owner_city,
                room_location,
                light_state,
                current_game,
                game_started_at,
                room_style,
                room_cleanliness,
                window_view,
                wall_color,
                desk_style,
                bed_style,
                current_entertainment_mode,
                current_entertainment_detail,
                current_entertainment_session,
                updated_at
            FROM home_world
            WHERE id = 1
            """
        )
        row = await cur.fetchone()

    tokyo_now = datetime.now(TOKYO_TZ)
    zhengzhou_now = datetime.now(ZHENGZHOU_TZ)

    return {
        "ying_city": row[0],
        "owner_city": row[1],
        "room_location": row[2],
        "light_state": row[3],
        "current_game": row[4],
        "game_started_at": row[5],
        "room_style": row[6],
        "room_cleanliness": row[7],
        "window_view": row[8],
        "wall_color": row[9],
        "desk_style": row[10],
        "bed_style": row[11],
        "current_entertainment_mode": row[12],
        "current_entertainment_detail": row[13],
        "current_entertainment_session": row[14],
        "updated_at": row[15],

        "tokyo_time": tokyo_now.isoformat(),
        "zhengzhou_time": zhengzhou_now.isoformat(),

        "tokyo_hour": tokyo_now.hour,
        "zhengzhou_hour": zhengzhou_now.hour,
    }


async def update_home_world(
    *,
    room_location=None,
    light_state=None,
    room_cleanliness=None,
    current_game=None,
    game_started_at=None,
    current_entertainment_mode=None,
    current_entertainment_detail=None,
    current_entertainment_session=None,
    clear_game=False,
):
    await init_home_world_db()

    current = await get_home_world()

    new_location = (
        current["room_location"]
        if room_location is None
        else room_location
    )

    new_light = (
        current["light_state"]
        if light_state is None
        else light_state
    )

    new_cleanliness = (
        current["room_cleanliness"]
        if room_cleanliness is None
        else room_cleanliness
    )

    if clear_game:
        new_game = None
        new_game_started_at = None
        new_ent_mode = None
        new_ent_detail = None
        new_ent_session = None
    else:
        new_game = (
            current["current_game"]
            if current_game is None
            else current_game
        )
        new_game_started_at = (
            current["game_started_at"]
            if game_started_at is None
            else game_started_at
        )
        new_ent_mode = (
            current["current_entertainment_mode"]
            if current_entertainment_mode is None
            else current_entertainment_mode
        )
        new_ent_detail = (
            current["current_entertainment_detail"]
            if current_entertainment_detail is None
            else current_entertainment_detail
        )
        new_ent_session = (
            current["current_entertainment_session"]
            if current_entertainment_session is None
            else current_entertainment_session
        )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE home_world
            SET room_location=?,
                light_state=?,
                room_cleanliness=?,
                current_game=?,
                game_started_at=?,
                current_entertainment_mode=?,
                current_entertainment_detail=?,
                current_entertainment_session=?,
                updated_at=?
            WHERE id=1
            """,
            (
                new_location,
                new_light,
                new_cleanliness,
                new_game,
                new_game_started_at,
                new_ent_mode,
                new_ent_detail,
                new_ent_session,
                datetime.now(TOKYO_TZ).isoformat(),
            )
        )
        await db.commit()

    return await get_home_world()


def room_location_for_activity(activity):
    mapping = {
        "gaming": "game_room",
        "reading": "study",
        "organizing": "study",
        "phone": "bedroom",
        "resting": "bedroom",
        "preparing_sleep": "bedroom",
        "sleeping": "bedroom",
        "dazing": "balcony",
        "listening": "living_room",
        "idle": "living_room",
        "eating": "kitchen",
        "washing": "bathroom",
    }

    return mapping.get(
        activity,
        "living_room",
    )
