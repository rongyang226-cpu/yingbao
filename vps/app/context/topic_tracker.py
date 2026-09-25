from __future__ import annotations

import re
from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


FOLLOWUP_MARKERS = (
    "这个", "那个", "刚才", "刚刚", "然后", "后来",
    "所以", "那", "它", "他", "她", "这件事", "那个事",
    "继续", "接着", "还有", "再说说", "为什么", "怎么",
)

STOPWORDS = {
    "什么", "怎么", "为什么", "可以", "这个", "那个",
    "然后", "还有", "就是", "一下", "现在", "今天",
    "明天", "刚才", "刚刚", "还是", "已经", "真的",
}

TOPIC_HINTS = (
    "联网搜索", "图片理解", "人物画像", "群聊", "天气",
    "提醒", "长期记忆", "记忆", "游戏", "虚拟恋人",
    "东京生活", "计划", "注意力", "关系", "权限",
)


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_topic_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS conversation_focus (
            person_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            topic TEXT,
            anchor_text TEXT,
            turns INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(person_id, platform, chat_id)
        );
        """)
        await db.commit()
def _extract_topic(text: str) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    # URL、命令、很短的语气词不作为话题名。
    if raw.startswith("/") or len(raw) <= 2:
        return None

    for hint in TOPIC_HINTS:
        if hint in raw:
            return hint

    latin = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]{2,}", raw)
    cjk = re.findall(r"[\u4e00-\u9fff]{2,8}", raw)

    candidates = []
    for item in latin + cjk:
        item = item.strip()
        if item in STOPWORDS:
            continue
        if any(sw in item and len(item) <= len(sw) + 1 for sw in STOPWORDS):
            continue
        candidates.append(item)

    if not candidates:
        compact = re.sub(r"[，。！？!?、：:；;\s]+", " ", raw).strip()
        return compact[:28] if compact else None

    # 优先更具体、长度适中的词组。
    candidates.sort(key=lambda x: (len(x), x), reverse=True)
    return candidates[0][:32]


def _is_followup(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if len(raw) <= 14:
        return True
    return any(marker in raw for marker in FOLLOWUP_MARKERS)


async def observe_topic(
    *,
    person_id: int,
    platform: str,
    chat_id,
    text: str,
):
    await init_topic_db()

    raw = str(text or "").strip()
    if not raw:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT topic, anchor_text, turns
            FROM conversation_focus
            WHERE person_id=? AND platform=? AND chat_id=?
            """,
            (int(person_id), str(platform), str(chat_id)),
        )
        row = await cur.fetchone()

        old_topic = row[0] if row else None
        turns = int(row[2] or 0) if row else 0

        new_topic = _extract_topic(raw)

        # 明确命中已知主题时允许短句直接换题；
        # 否则短追问优先延续上一话题，避免“为什么/然后呢”覆盖焦点。
        if new_topic in TOPIC_HINTS:
            topic = new_topic
        elif old_topic and _is_followup(raw):
            topic = old_topic
        else:
            topic = new_topic or old_topic

        if not topic:
            return None

        await db.execute(
            """
            INSERT INTO conversation_focus (
                person_id, platform, chat_id,
                topic, anchor_text, turns, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(person_id, platform, chat_id)
            DO UPDATE SET
                topic=excluded.topic,
                anchor_text=excluded.anchor_text,
                turns=conversation_focus.turns+1,
                updated_at=excluded.updated_at
            """,
            (
                int(person_id),
                str(platform),
                str(chat_id),
                topic,
                raw[:500],
                now(),
            ),
        )
        await db.commit()

    return topic


async def get_topic_context(
    *,
    person_id: int,
    platform: str,
    chat_id,
):
    await init_topic_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT topic, anchor_text, turns, updated_at
            FROM conversation_focus
            WHERE person_id=? AND platform=? AND chat_id=?
            """,
            (int(person_id), str(platform), str(chat_id)),
        )
        row = await cur.fetchone()

    if not row:
        return "当前没有明确延续中的话题。"

    topic, anchor, turns, updated_at = row

    return (
        f"当前延续话题：{topic}\n"
        f"最近锚点：{anchor}\n"
        f"已连续观察约 {int(turns or 0)} 轮。\n"
        "如果本轮明显换了话题，以当前消息为准；"
        "如果只是“然后呢/为什么/这个呢”之类短追问，优先承接这个话题。"
    )
