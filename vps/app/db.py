import aiosqlite
import hashlib
from app.config import DB_PATH


def group_identity_tag(chat_id, user_id):
    """Stable, group-scoped speaker label; never identifies a person by nickname."""
    raw = f"{chat_id}\0{user_id}".encode("utf-8")
    return "成员#" + hashlib.blake2s(raw, digest_size=5).hexdigest()


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    person_id INTEGER,
    message_id INTEGER,
    reply_to_message_id INTEGER,
    reply_to_user_id TEXT,
    reply_to_name TEXT
);

CREATE TABLE IF NOT EXISTS privacy_sessions (
    platform TEXT NOT NULL,
    user_id TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'off',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (platform, user_id)
);

CREATE TABLE IF NOT EXISTS command_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    user_id TEXT NOT NULL,
    command TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_chat
ON messages(platform, chat_id, id);
"""


async def init_db():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    async with aiosqlite.connect(DB_PATH) as db:
        # 1. 创建基础表。
        await db.executescript(SCHEMA)

        # 2. 兼容旧版 messages 数据库。
        cur = await db.execute(
            "PRAGMA table_info(messages)"
        )
        columns = {
            row[1]
            for row in await cur.fetchall()
        }

        migrations = {
            "person_id":
                "ALTER TABLE messages ADD COLUMN person_id INTEGER",
            "message_id":
                "ALTER TABLE messages ADD COLUMN message_id INTEGER",
            "reply_to_message_id":
                "ALTER TABLE messages ADD COLUMN reply_to_message_id INTEGER",
            "reply_to_user_id":
                "ALTER TABLE messages ADD COLUMN reply_to_user_id TEXT",
            "reply_to_name":
                "ALTER TABLE messages ADD COLUMN reply_to_name TEXT",
        }

        for column, sql in migrations.items():
            if column not in columns:
                await db.execute(sql)

        # 3. 防止同一平台消息重复写入。
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_messages_platform_chat_message_role
            ON messages(
                platform,
                chat_id,
                message_id,
                role
            )
            WHERE message_id IS NOT NULL
        """)

        # 4. 这些表由对应模块创建。
        #    仅在表已经存在时固化其幂等索引。
        cur = await db.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
        """)
        tables = {
            row[0]
            for row in await cur.fetchall()
        }

        if "state_history" in tables:
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                uq_relationship_source_event
                ON state_history(
                    person_id,
                    state_type,
                    source_platform,
                    source_chat_id,
                    source_message_id,
                    reason
                )
                WHERE source_message_id IS NOT NULL
                  AND state_type='relationship'
            """)

        if "events" in tables:
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                uq_events_source_event
                ON events(
                    person_id,
                    event_type,
                    source_platform,
                    source_chat_id,
                    source_message_id
                )
                WHERE source_message_id IS NOT NULL
            """)

        await db.commit()

async def save_message(
    platform,
    chat_id,
    user_id,
    username,
    role,
    content,
    person_id=None,
    message_id=None,
    reply_to_message_id=None,
    reply_to_user_id=None,
    reply_to_name=None
):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO messages (
                platform,
                chat_id,
                user_id,
                username,
                role,
                content,
                person_id,
                message_id,
                reply_to_message_id,
                reply_to_user_id,
                reply_to_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                str(chat_id),
                str(user_id),
                username,
                role,
                content,
                person_id,
                message_id,
                reply_to_message_id,
                reply_to_user_id,
                reply_to_name
            )
        )
        await db.commit()

        # True = 首次写入
        # False = 同一平台/聊天/message_id/role 已经存在
        return cur.rowcount > 0



async def reset_private_chat_history(platform: str, chat_id: str, user_id: str) -> int:
    """仅清理请求者本人对应的私聊消息，不触碰记忆、其他会话或审计。"""
    platform = str(platform)
    chat_id = str(chat_id)
    user_id = str(user_id)
    if platform == "telegram" and chat_id != user_id:
        raise ValueError("只允许清理自己的 Telegram 私聊")
    if platform == "mobile" and chat_id != f"mobile:{user_id}":
        raise ValueError("只允许清理自己的手机私聊")
    if platform not in {"telegram", "mobile"}:
        raise ValueError("不支持的平台")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM messages WHERE platform=? AND chat_id=?",
            (platform, chat_id),
        )
        await db.commit()
        return cur.rowcount


async def get_history(
    platform,
    chat_id,
    limit=20,
    exclude_message_id=None,
    focus_user_id=None,
):
    is_group = str(chat_id).startswith("-")

    async with aiosqlite.connect(DB_PATH) as db:
        where_extra = ""
        params = [platform, str(chat_id)]

        if exclude_message_id is not None:
            where_extra = """
              AND (
                  m.message_id IS NULL
                  OR m.message_id != ?
              )
            """
            params.append(exclude_message_id)

        fetch_limit = limit
        if is_group and focus_user_id is not None:
            fetch_limit = max(limit * 4, 60)

        params.append(fetch_limit)

        cur = await db.execute(
            f"""
            SELECT
                m.role,
                m.content,
                m.user_id,
                COALESCE(i.display_name, m.username),
                COALESCE(i.username, m.username),
                m.person_id,
                m.reply_to_user_id,
                m.reply_to_name
            FROM messages m
            LEFT JOIN identities i
              ON i.platform = m.platform
             AND i.platform_user_id = m.user_id
            WHERE m.platform=?
              AND m.chat_id=?
              {where_extra}
            ORDER BY m.id DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cur.fetchall()

    rows.reverse()

    if is_group and focus_user_id is not None and len(rows) > limit:
        focus = str(focus_user_id)
        recent_ids = set(range(max(0, len(rows) - 12), len(rows)))
        focused_ids = []

        for idx, row in enumerate(rows):
            user_id = str(row[2] or "")
            reply_to_user_id = str(row[6] or "")
            if user_id == focus or reply_to_user_id == focus:
                focused_ids.append(idx)

        keep = recent_ids | set(focused_ids[-12:])
        rows = [
            row
            for idx, row in enumerate(rows)
            if idx in keep
        ]

        if len(rows) > 24:
            rows = rows[-24:]

    history = []

    for row in rows:
        (
            role,
            content,
            user_id,
            speaker_name,
            speaker_username,
            person_id,
            reply_to_user_id,
            reply_to_name,
        ) = row

        if not is_group:
            if role == "assistant":
                history.append({
                    "role": "assistant",
                    "content": content,
                })
            else:
                history.append({
                    "role": "user",
                    "content": content,
                })
            continue

        # 群聊里必须保留“谁在说、在回复谁”，否则多人并行聊天
        # 很容易把不同人的上下文串在一起。
        if role == "assistant":
            target = (
                f"[萤 -> {group_identity_tag(chat_id, reply_to_user_id)}] "
                if platform == "telegram" and reply_to_user_id else ""
            )
            history.append({
                "role": "assistant",
                "content": target + content,
            })
        else:
            if (
                str(user_id) == "1087968824"
                or str(speaker_username or "") == "GroupAnonymousBot"
            ):
                label = "匿名管理员（旧记录，具体身份不可恢复）"
            else:
                label = speaker_name or "群成员"

                if (
                    speaker_username
                    and not str(speaker_username).startswith("匿名管理员")
                    and str(speaker_username) != str(speaker_name)
                ):
                    label += f" (@{speaker_username})"

            if platform == "telegram":
                label = f"{group_identity_tag(chat_id, user_id)} {label}"
                if reply_to_user_id:
                    label += f" -> 回复 {group_identity_tag(chat_id, reply_to_user_id)} {reply_to_name or '成员'}"
                elif reply_to_name:
                    label += f" -> 回复 {reply_to_name}"
            elif reply_to_name:
                label += f" -> 回复 {reply_to_name}"
            history.append({
                "role": "user",
                "content": f"[{label}] {content}",
            })

    return history


async def get_person_private_history(
    person_id,
    limit=20,
    exclude_platform=None,
    exclude_message_id=None,
):
    """合并同一人物在 Telegram 私聊与手机端的最近对话。"""
    conditions = [
        "person_id = ?",
        "role IN ('user', 'assistant')",
        "((platform='telegram' AND CAST(chat_id AS TEXT) NOT LIKE '-%') OR platform='mobile')",
    ]
    params = [int(person_id)]

    if exclude_platform is not None and exclude_message_id is not None:
        conditions.append(
            "NOT (platform = ? AND message_id = ?)"
        )
        params.extend([str(exclude_platform), exclude_message_id])

    params.append(int(limit))

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            f"""
            SELECT role, content, platform
            FROM messages
            WHERE {' AND '.join(conditions)}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cur.fetchall()

    rows.reverse()
    return [
        {
            "role": "assistant" if role == "assistant" else "user",
            "content": content,
        }
        for role, content, _platform in rows
    ]


async def audit(
    platform,
    user_id,
    command,
    allowed
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO command_audit
            (platform, user_id, command, allowed)
            VALUES (?, ?, ?, ?)
            """,
            (
                platform,
                str(user_id),
                command,
                int(bool(allowed))
            )
        )
        await db.commit()


async def get_message_reply_target(
    platform,
    chat_id,
    message_id,
):
    """
    查询某条已保存消息当时直接回复的对象。
    只用于身份/引用链解析，不修改任何数据。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                reply_to_user_id,
                reply_to_name,
                user_id,
                username,
                role
            FROM messages
            WHERE platform=?
              AND chat_id=?
              AND message_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                platform,
                chat_id,
                message_id,
            ),
        )
        row = await cur.fetchone()

    if not row:
        return None

    return {
        "reply_to_user_id": row[0],
        "reply_to_name": row[1],
        "message_user_id": row[2],
        "message_username": row[3],
        "role": row[4],
    }
