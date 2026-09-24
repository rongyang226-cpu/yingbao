def normalize_query(text: str) -> str:
    return (
        (text or "")
        .replace("？", "")
        .replace("?", "")
        .replace("。", "")
        .strip()
    )


def detect_recent_query(text: str):
    """
    判断用户是不是在询问确定性的近期聊天事实。

    返回：
        recent_group_message
        recent_private_message
        None
    """

    text = normalize_query(text)

    recent = (
        "刚刚" in text
        or "刚才" in text
        or "刚" in text
    )

    asks_message = (
        "说了什么" in text
        or "说了啥" in text
        or "说什么" in text
        or "发了什么" in text
        or "发了啥" in text
    )

    if not (recent and asks_message):
        return None

    if "群" in text:
        return "recent_group_message"

    if "私聊" in text:
        return "recent_private_message"

    return None


def find_recent_message(
    runtime_context: dict,
    source: str,
    current_message_id=None,
):
    """
    从 ContextBuilder 已经取得的近期活动中查询。
    不再次访问数据库。
    """

    activities = runtime_context.get(
        "recent_activity",
        []
    )

    # ContextBuilder 输出为旧 -> 新，
    # 所以反向遍历得到最近一条。
    for item in reversed(activities):

        if (
            current_message_id is not None
            and item.get("message_id")
            == current_message_id
        ):
            continue

        if source == "group":
            if item.get("source") == "group":
                return item

        elif source == "private":
            chat_id = str(
                item.get("chat_id", "")
            )

            if not chat_id.startswith("-"):
                return item

    return None


async def find_recent_message_db(
    *,
    person_id: int,
    source: str,
    current_chat_id=None,
    platform: str = "telegram",
    exclude_message_id=None,
):
    """
    直接从完整消息数据库查询最近消息。

    与 ContextBuilder 的模型上下文窗口完全独立。
    """
    import aiosqlite
    from app.config import DB_PATH

    conditions = [
        "person_id = ?",
        "role = 'user'",
    ]
    params = [person_id]

    if platform == "shared_private":
        conditions.append("platform IN ('telegram', 'mobile')")
    else:
        conditions.insert(0, "platform = ?")
        params.insert(0, platform)

    if source == "group":
        if current_chat_id is not None:
            # 群聊硬隔离：只允许查询当前群。
            conditions.append("chat_id = ?")
            params.append(str(current_chat_id))
        else:
            # 兼容旧调用。
            conditions.append(
                "CAST(chat_id AS TEXT) LIKE '-%'"
            )

    elif source == "private":
        conditions.append(
            "CAST(chat_id AS TEXT) NOT LIKE '-%'"
        )

    else:
        return None

    if exclude_message_id is not None:
        conditions.append(
            "(message_id IS NULL OR message_id != ?)"
        )
        params.append(exclude_message_id)

    sql = f"""
        SELECT
            chat_id,
            message_id,
            content,
            created_at
        FROM messages
        WHERE {' AND '.join(conditions)}
        ORDER BY id DESC
        LIMIT 1
    """

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(sql, params)
        row = await cur.fetchone()

    if not row:
        return None

    return {
        "chat_id": row[0],
        "message_id": row[1],
        "content": row[2],
        "created_at": row[3],
        "source": source,
    }


async def list_recent_messages_db(
    *,
    person_id: int,
    source: str,
    current_chat_id=None,
    platform: str = "telegram",
    exclude_message_id=None,
    limit: int = 8,
):
    """
    查询某个人在指定场景最近说过的若干条消息。
    不受 ContextBuilder 窗口限制。
    """
    import aiosqlite
    from app.config import DB_PATH

    conditions = [
        "person_id = ?",
        "role = 'user'",
    ]
    params = [person_id]

    if platform == "shared_private":
        conditions.append("platform IN ('telegram', 'mobile')")
    else:
        conditions.insert(0, "platform = ?")
        params.insert(0, platform)

    if source == "group":
        if current_chat_id is not None:
            # 群聊硬隔离：只允许查询当前群。
            conditions.append("chat_id = ?")
            params.append(str(current_chat_id))
        else:
            conditions.append(
                "CAST(chat_id AS TEXT) LIKE '-%'"
            )

    elif source == "private":
        conditions.append(
            "CAST(chat_id AS TEXT) NOT LIKE '-%'"
        )

    else:
        return []

    if exclude_message_id is not None:
        conditions.append(
            "(message_id IS NULL OR message_id != ?)"
        )
        params.append(exclude_message_id)

    params.append(limit)

    sql = f"""
        SELECT
            id,
            chat_id,
            message_id,
            content,
            created_at
        FROM messages
        WHERE {' AND '.join(conditions)}
        ORDER BY id DESC
        LIMIT ?
    """

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()

    return [
        {
            "id": row[0],
            "chat_id": row[1],
            "message_id": row[2],
            "content": row[3],
            "created_at": row[4],
            "source": source,
        }
        for row in rows
    ]
