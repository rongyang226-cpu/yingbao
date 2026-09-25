import aiosqlite
from datetime import datetime, timezone

from app.config import DB_PATH


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_events_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            person_id INTEGER NOT NULL,

            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT,

            status TEXT NOT NULL DEFAULT 'open',

            priority INTEGER NOT NULL DEFAULT 0,

            due_at TEXT,

            source_platform TEXT,
            source_chat_id TEXT,
            source_message_id INTEGER,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,

            FOREIGN KEY(person_id)
                REFERENCES people(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_person_status
        ON events(person_id, status);

        CREATE INDEX IF NOT EXISTS idx_events_due
        ON events(due_at);

        CREATE INDEX IF NOT EXISTS idx_events_source
        ON events(
            source_platform,
            source_chat_id,
            source_message_id
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_events_source_event
        ON events(
            person_id,
            event_type,
            source_platform,
            source_chat_id,
            source_message_id
        )
        WHERE source_message_id IS NOT NULL;
        """)

        await db.commit()


async def add_event(
    *,
    person_id: int,
    event_type: str,
    title: str,
    details=None,
    priority: int = 0,
    due_at=None,
    source_platform=None,
    source_chat_id=None,
    source_message_id=None,
):
    """
    创建事件。

    当 source_message_id 存在时，同一来源事件具有幂等性：
    重复调用不会创建第二条事件，而是返回原 event_id。
    """
    t = now()

    source_chat = (
        str(source_chat_id)
        if source_chat_id is not None
        else None
    )

    async with aiosqlite.connect(DB_PATH) as db:
        # 有明确来源消息时使用数据库唯一约束实现原子幂等。
        if source_message_id is not None:
            await db.execute(
                """
                INSERT OR IGNORE INTO events (
                    person_id,
                    event_type,
                    title,
                    details,
                    status,
                    priority,
                    due_at,
                    source_platform,
                    source_chat_id,
                    source_message_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_id,
                    event_type,
                    title,
                    details,
                    priority,
                    due_at,
                    source_platform,
                    source_chat,
                    source_message_id,
                    t,
                    t,
                )
            )

            cur = await db.execute(
                """
                SELECT id
                FROM events
                WHERE person_id=?
                  AND event_type=?
                  AND source_platform IS ?
                  AND source_chat_id IS ?
                  AND source_message_id=?
                LIMIT 1
                """,
                (
                    person_id,
                    event_type,
                    source_platform,
                    source_chat,
                    source_message_id,
                )
            )

            row = await cur.fetchone()
            await db.commit()

            if row is None:
                raise RuntimeError(
                    "event insert succeeded but event could not be resolved"
                )

            return row[0]

        # 没有来源 message_id 的内部事件仍按普通方式创建。
        cur = await db.execute(
            """
            INSERT INTO events (
                person_id,
                event_type,
                title,
                details,
                status,
                priority,
                due_at,
                source_platform,
                source_chat_id,
                source_message_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                event_type,
                title,
                details,
                priority,
                due_at,
                source_platform,
                source_chat,
                source_message_id,
                t,
                t,
            )
        )

        await db.commit()
        return cur.lastrowid


async def claim_event(event_id: int):
    """
    原子抢占一个 open 事件。
    True = 当前 worker 获得发送权
    False = 已被其他 worker/状态抢走
    """
    t = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE events
            SET status='delivering',
                updated_at=?
            WHERE id=?
              AND status='open'
            """,
            (t, event_id)
        )

        await db.commit()
        return cur.rowcount > 0


async def release_event(event_id: int):
    """
    发送明确失败时，把 delivering 退回 open，
    允许下一轮重新尝试。
    """
    t = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE events
            SET status='open',
                updated_at=?
            WHERE id=?
              AND status='delivering'
            """,
            (t, event_id)
        )

        await db.commit()
        return cur.rowcount > 0


async def complete_event(event_id: int):
    t = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE events
            SET status='completed',
                completed_at=?,
                updated_at=?
            WHERE id=?
              AND status IN ('open', 'delivering')
            """,
            (t, t, event_id)
        )

        await db.commit()

        return cur.rowcount > 0


async def cancel_event(event_id: int):
    t = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE events
            SET status='cancelled',
                updated_at=?
            WHERE id=?
              AND status='open'
            """,
            (t, event_id)
        )

        await db.commit()

        return cur.rowcount > 0


async def get_open_events(
    person_id: int,
    limit: int = 20,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                id,
                event_type,
                title,
                details,
                priority,
                due_at,
                created_at
            FROM events
            WHERE person_id=?
              AND status='open'
            ORDER BY
                priority DESC,
                CASE
                    WHEN due_at IS NULL THEN 1
                    ELSE 0
                END,
                due_at ASC,
                id DESC
            LIMIT ?
            """,
            (person_id, limit)
        )

        rows = await cur.fetchall()

    return [
        {
            "id": row[0],
            "type": row[1],
            "title": row[2],
            "details": row[3],
            "priority": row[4],
            "due_at": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


async def build_event_context(
    person_id: int,
    limit: int = 10,
):
    events = await get_open_events(
        person_id,
        limit
    )

    if not events:
        return "当前没有未完成事件。"

    lines = []

    for event in events:
        line = (
            f"- #{event['id']} "
            f"[{event['type']}] "
            f"{event['title']}"
        )

        if event["due_at"]:
            line += f" | due={event['due_at']}"

        if event["details"]:
            line += f" | {event['details']}"

        lines.append(line)

    return "\n".join(lines)


async def add_reminder(
    *,
    person_id: int,
    title: str,
    due_at: str,
    details=None,
    source_platform=None,
    source_chat_id=None,
    source_message_id=None,
):
    """
    创建一个确定时间的提醒事件。

    due_at 必须使用 UTC ISO 8601。
    """
    if not title or not title.strip():
        raise ValueError("reminder title cannot be empty")

    if not due_at:
        raise ValueError("reminder due_at cannot be empty")

    return await add_event(
        person_id=person_id,
        event_type="reminder",
        title=title.strip(),
        details=details,
        priority=10,
        due_at=due_at,
        source_platform=source_platform,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
    )


async def get_due_events(limit: int = 50):
    """
    获取已经到期、仍处于 open 状态的事件。

    events.due_at 使用 UTC ISO 8601。
    """
    current = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                id,
                person_id,
                event_type,
                title,
                details,
                priority,
                due_at,
                source_platform,
                source_chat_id,
                source_message_id,
                created_at
            FROM events
            WHERE status='open'
              AND due_at IS NOT NULL
              AND due_at <= ?
            ORDER BY
                priority DESC,
                due_at ASC,
                id ASC
            LIMIT ?
            """,
            (current, limit)
        )

        rows = await cur.fetchall()

    return [
        {
            "id": row[0],
            "person_id": row[1],
            "type": row[2],
            "title": row[3],
            "details": row[4],
            "priority": row[5],
            "due_at": row[6],
            "source_platform": row[7],
            "source_chat_id": row[8],
            "source_message_id": row[9],
            "created_at": row[10],
        }
        for row in rows
    ]
