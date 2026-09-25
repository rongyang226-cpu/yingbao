import aiosqlite
from datetime import datetime, timezone

from app.config import DB_PATH, TELEGRAM_OWNER_ID


async def init_people_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS people (
            person_id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT,
            role TEXT NOT NULL DEFAULT 'USER',
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS identities (
            platform TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            username TEXT,
            display_name TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,

            PRIMARY KEY (platform, platform_user_id),

            FOREIGN KEY (person_id)
                REFERENCES people(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_identity_person
        ON identities(person_id);
        """)
        await db.commit()


def now():
    return datetime.now(timezone.utc).isoformat()


async def get_or_create_person(
    platform,
    user_id,
    username=None,
    display_name=None
):
    platform = str(platform)
    user_id = str(user_id)

    # OWNER 只认稳定数字 ID
    is_owner = (
        platform == "telegram"
        and user_id == str(TELEGRAM_OWNER_ID)
    )

    async with aiosqlite.connect(DB_PATH) as db:

        cur = await db.execute(
            """
            SELECT
                p.person_id,
                p.role,
                p.display_name
            FROM identities i
            JOIN people p
              ON p.person_id = i.person_id
            WHERE i.platform = ?
              AND i.platform_user_id = ?
            """,
            (platform, user_id)
        )

        row = await cur.fetchone()

        if row:
            person_id, role, old_name = row

            # OWNER 权限由配置强制纠正
            if is_owner and role != "OWNER":
                role = "OWNER"
                await db.execute(
                    "UPDATE people SET role = ? WHERE person_id = ?",
                    ("OWNER", person_id)
                )

            await db.execute(
                """
                UPDATE identities
                SET username = COALESCE(?, username),
                    display_name = COALESCE(?, display_name),
                    last_seen = ?
                WHERE platform = ?
                  AND platform_user_id = ?
                """,
                (
                    username,
                    display_name,
                    now(),
                    platform,
                    user_id
                )
            )

            await db.execute(
                """
                UPDATE people
                SET display_name = ?,
                    last_seen = ?
                WHERE person_id = ?
                """,
                (
                    display_name or old_name,
                    now(),
                    person_id
                )
            )

            await db.commit()

            return {
                "person_id": person_id,
                "role": role,
                "display_name": display_name or old_name
            }

        role = "OWNER" if is_owner else "USER"
        t = now()

        cur = await db.execute(
            """
            INSERT INTO people
            (display_name, role, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            """,
            (
                display_name,
                role,
                t,
                t
            )
        )

        person_id = cur.lastrowid

        await db.execute(
            """
            INSERT INTO identities
            (
                platform,
                platform_user_id,
                person_id,
                username,
                display_name,
                first_seen,
                last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                user_id,
                person_id,
                username,
                display_name,
                t,
                t
            )
        )

        await db.commit()

        return {
            "person_id": person_id,
            "role": role,
            "display_name": display_name
        }


async def get_person_by_identity(platform, user_id):
    """
    只读获取稳定人物身份，不修改 username/display_name/last_seen。
    适合后台 worker 使用，避免主动任务把真实身份字段覆盖成占位值。
    """
    platform = str(platform)
    user_id = str(user_id)

    await init_people_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                p.person_id,
                p.role,
                p.display_name,
                i.username,
                i.display_name
            FROM identities i
            JOIN people p
              ON p.person_id=i.person_id
            WHERE i.platform=?
              AND i.platform_user_id=?
            """,
            (platform, user_id),
        )
        row = await cur.fetchone()

    if not row:
        return None

    person_id, role, person_name, username, identity_name = row

    return {
        "person_id": person_id,
        "role": role,
        "display_name": identity_name or person_name,
        "username": username,
        "platform_user_id": user_id,
    }
