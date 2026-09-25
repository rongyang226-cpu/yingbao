import aiosqlite

from app.config import DB_PATH


async def init_fts():
    """
    创建聊天历史全文索引。
    原始 messages 表仍然是真实数据源。
    FTS 只是搜索索引。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
            USING fts5(
                content,
                content='messages',
                content_rowid='id',
                tokenize='unicode61'
            )
        """)

        # messages -> FTS 自动同步
        await db.executescript("""
            CREATE TRIGGER IF NOT EXISTS messages_fts_ai
            AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content)
                VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_fts_ad
            AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(
                    messages_fts,
                    rowid,
                    content
                )
                VALUES (
                    'delete',
                    old.id,
                    old.content
                );
            END;

            CREATE TRIGGER IF NOT EXISTS messages_fts_au
            AFTER UPDATE OF content ON messages BEGIN
                INSERT INTO messages_fts(
                    messages_fts,
                    rowid,
                    content
                )
                VALUES (
                    'delete',
                    old.id,
                    old.content
                );

                INSERT INTO messages_fts(rowid, content)
                VALUES (new.id, new.content);
            END;
        """)

        # 给已有聊天建立索引
        await db.execute("""
            INSERT INTO messages_fts(messages_fts)
            VALUES ('rebuild')
        """)

        await db.commit()


def _fts_query(text: str) -> str:
    """
    生成较保守的 FTS 查询。
    """
    words = [
        x.strip()
        for x in text.replace("？", " ")
                     .replace("?", " ")
                     .replace("。", " ")
                     .replace("，", " ")
                     .split()
        if x.strip()
    ]

    if not words:
        return ""

    # 对用户输入加引号，避免把 FTS 运算符直接带进去
    return " OR ".join(
        '"' + x.replace('"', '""') + '"'
        for x in words
    )


async def search_messages_fts(
    *,
    person_id: int,
    query: str,
    platform: str = "telegram",
    chat_id=None,
    limit: int = 10,
):
    q = _fts_query(query)

    if not q:
        return []

    conditions = [
        "m.platform = ?",
        "m.person_id = ?",
        "m.role = 'user'",
        "messages_fts MATCH ?",
    ]

    params = [
        platform,
        person_id,
        q,
    ]

    if chat_id is not None:
        conditions.append("m.chat_id = ?")
        params.append(str(chat_id))

    params.append(limit)

    sql = f"""
        SELECT
            m.id,
            m.chat_id,
            m.message_id,
            m.content,
            m.created_at,
            bm25(messages_fts) AS score
        FROM messages_fts
        JOIN messages AS m
          ON m.id = messages_fts.rowid
        WHERE {' AND '.join(conditions)}
        ORDER BY score
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
            "score": row[5],
        }
        for row in rows
    ]
