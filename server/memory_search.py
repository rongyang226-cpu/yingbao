import aiosqlite
from app.config import DB_PATH


async def search_history(
    person_id,
    query,
    platform="telegram",
    limit=10
):
    """
    搜索某个人自己的历史消息。
    person_id 是身份边界，避免串到其他人的私有历史。
    """

    query = (query or "").strip()

    if not query:
        return []

    async with aiosqlite.connect(DB_PATH) as db:

        # 第一层：直接关键词搜索
        cur = await db.execute(
            """
            SELECT
                id,
                chat_id,
                content,
                created_at,
                message_id
            FROM messages
            WHERE platform=?
              AND person_id=?
              AND role='user'
              AND content LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                platform,
                person_id,
                f"%{query}%",
                limit
            )
        )

        rows = await cur.fetchall()

        # 找不到时，把问题拆成几个词再尝试
        if not rows:
            words = [
                x.strip()
                for x in query
                .replace("？", " ")
                .replace("?", " ")
                .replace("，", " ")
                .replace(",", " ")
                .split()
                if len(x.strip()) >= 2
            ]

            found = []

            for word in words[:5]:
                cur = await db.execute(
                    """
                    SELECT
                        id,
                        chat_id,
                        content,
                        created_at,
                        message_id
                    FROM messages
                    WHERE platform=?
                      AND person_id=?
                      AND role='user'
                      AND content LIKE ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (
                        platform,
                        person_id,
                        f"%{word}%",
                        limit
                    )
                )

                found.extend(
                    await cur.fetchall()
                )

            # 去重
            seen = set()
            rows = []

            for row in found:
                if row[0] in seen:
                    continue

                seen.add(row[0])
                rows.append(row)

                if len(rows) >= limit:
                    break

    return [
        {
            "db_id": row[0],
            "chat_id": row[1],
            "content": row[2],
            "created_at": row[3],
            "message_id": row[4]
        }
        for row in rows
    ]


async def search_group_history(
    chat_id,
    query,
    platform="telegram",
    limit=10
):
    """
    只搜索指定群自己的公开历史。
    不允许跨 chat_id 搜索。
    """

    query = (query or "").strip()

    if not query:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                id,
                user_id,
                username,
                content,
                created_at,
                message_id
            FROM messages
            WHERE platform=?
              AND chat_id=?
              AND content LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                platform,
                str(chat_id),
                f"%{query}%",
                limit
            )
        )

        rows = await cur.fetchall()

    return [
        {
            "db_id": row[0],
            "user_id": row[1],
            "username": row[2],
            "content": row[3],
            "created_at": row[4],
            "message_id": row[5]
        }
        for row in rows
    ]


async def search_person_history_anywhere(
    person_id,
    query,
    current_chat_id,
    platform="telegram",
    limit=10
):
    """
    搜索同一人物跨聊天空间的历史。

    返回时明确标记：
    - current: 当前聊天
    - private: 私聊
    - group: 其他群聊

    注意：
    这里只负责找记录。
    是否允许在当前场景说出来，由上层决定。
    """

    query = (query or "").strip()

    if not query:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                id,
                chat_id,
                user_id,
                username,
                content,
                created_at,
                message_id
            FROM messages
            WHERE platform=?
              AND person_id=?
              AND role='user'
              AND content LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                platform,
                person_id,
                f"%{query}%",
                limit
            )
        )

        rows = await cur.fetchall()

    result = []

    for row in rows:
        chat_id = str(row[1])
        current = str(current_chat_id)

        if chat_id == current:
            source_type = "current"
        elif chat_id.startswith("-"):
            source_type = "group"
        else:
            source_type = "private"

        result.append({
            "db_id": row[0],
            "chat_id": row[1],
            "user_id": row[2],
            "username": row[3],
            "content": row[4],
            "created_at": row[5],
            "message_id": row[6],
            "source_type": source_type
        })

    return result


async def get_recent_person_activity(
    person_id,
    current_chat_id,
    platform="telegram",
    limit=12
):
    """
    获取同一人物最近跨聊天空间的真实发言。
    用于理解“刚才”“之前”“群里刚说了什么”等问题。
    """

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                id,
                chat_id,
                content,
                created_at,
                message_id
            FROM messages
            WHERE platform=?
              AND person_id=?
              AND role='user'
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                platform,
                person_id,
                limit
            )
        )

        rows = await cur.fetchall()

    result = []

    for row in rows:
        chat_id = str(row[1])
        current = str(current_chat_id)

        if chat_id == current:
            source_type = "current"
        elif chat_id.startswith("-"):
            source_type = "group"
        else:
            source_type = "private"

        result.append({
            "db_id": row[0],
            "chat_id": row[1],
            "content": row[2],
            "created_at": row[3],
            "message_id": row[4],
            "source_type": source_type
        })

    return result


async def search_messages_cn(
    *,
    person_id: int,
    query: str,
    platform: str = "telegram",
    chat_id=None,
    limit: int = 10,
):
    """
    中文聊天历史检索。

    原则：
    - messages 是事实源
    - 中文使用 LIKE，不依赖 FTS 分词
    - 先召回较多候选，再由程序排序
    - 原始陈述优先
    - 回忆/查询型消息降权
    """
    import re
    import aiosqlite
    from app.config import DB_PATH

    text = (query or "").strip()
    if not text:
        return []

    # 去掉“回忆请求”的语言外壳，尽量留下主题。
    noise = (
        "你知道",
        "你还记得",
        "还记得",
        "我记得",
        "我们以前",
        "我们之前",
        "我刚刚",
        "我刚才",
        "刚刚",
        "刚才",
        "以前",
        "之前",
        "曾经",
        "在哪里",
        "在哪儿",
        "在哪",
        "哪里",
        "是不是",
        "有没有",
        "有聊过",
        "聊过",
        "说过",
        "提过",
        "提到过",
        "记得",
        "记不记得",
        "帮我找",
        "找找",
        "查一下",
        "的内容",
        "什么",
        "了吗",
        "了么",
        "吗",
        "呢",
        "？",
        "?",
        "，",
        ",",
    )

    cleaned = text
    for word in noise:
        cleaned = cleaned.replace(word, " ")

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    terms = re.findall(
        r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_.+-]{2,}",
        cleaned,
    )

    if not terms:
        terms = re.findall(
            r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_.+-]{2,}",
            text,
        )

    if not terms:
        return []

    terms = terms[:5]

    conditions = [
        "person_id = ?",
        "role = 'user'",
    ]
    params = [person_id]

    if platform == "shared_private":
        conditions.append("platform IN ('telegram', 'mobile')")
        conditions.append("CAST(chat_id AS TEXT) NOT LIKE '-%'")
    else:
        conditions.append("platform = ?")
        params.append(platform)

    if chat_id is not None and platform != "shared_private":
        conditions.append("chat_id = ?")
        params.append(str(chat_id))

    like_parts = []
    for term in terms:
        like_parts.append("content LIKE ?")
        params.append(f"%{term}%")

    conditions.append(
        "(" + " OR ".join(like_parts) + ")"
    )

    # 多召回一些，再在 Python 中排序。
    fetch_limit = max(limit * 6, 40)
    params.append(fetch_limit)

    sql = f"""
        SELECT
            id,
            chat_id,
            message_id,
            role,
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

    question_markers = (
        "你知道",
        "你记得",
        "还记得",
        "记不记得",
        "在哪里",
        "在哪儿",
        "在哪",
        "哪里",
        "是不是",
        "有没有",
        "说了什么",
        "说了啥",
        "说过什么",
        "说过啥",
        "帮我找",
        "找找",
        "查一下",
        "吗",
        "呢",
        "?",
        "？",
    )

    def score(row):
        content = (row[4] or "").strip()

        # 主题词命中数量。
        hits = sum(
            1 for term in terms
            if term in content
        )

        value = hits * 100

        # 内容越接近纯主题陈述越好。
        if cleaned and cleaned in content:
            value += 80

        # 完全等于主题，通常就是最干净的原始陈述。
        if cleaned and content == cleaned:
            value += 160

        # 查询/回忆型消息降权，避免命中“我刚才在哪说……”
        if any(
            marker in content
            for marker in question_markers
        ):
            value -= 120

        # 与当前查询完全相同，强烈降权。
        if content == text:
            value -= 300

        # 同分时仍优先较新的真实记录。
        return (value, row[0])

    rows.sort(
        key=score,
        reverse=True,
    )

    rows = rows[:limit]

    return [
        {
            "id": row[0],
            "chat_id": row[1],
            "message_id": row[2],
            "role": row[3],
            "content": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]
