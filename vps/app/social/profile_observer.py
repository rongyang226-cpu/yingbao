from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


def now():
    return datetime.now(timezone.utc).isoformat()


async def init_profile_observer_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS person_style_stats (
            person_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            total_chars INTEGER NOT NULL DEFAULT 0,
            question_count INTEGER NOT NULL DEFAULT 0,
            emoji_like_count INTEGER NOT NULL DEFAULT 0,
            mention_count INTEGER NOT NULL DEFAULT 0,
            reply_count INTEGER NOT NULL DEFAULT 0,
            short_count INTEGER NOT NULL DEFAULT 0,
            long_count INTEGER NOT NULL DEFAULT 0,
            last_message_at TEXT,
            PRIMARY KEY(person_id, platform, chat_id)
        );
        """)
        await db.commit()


def _emoji_like(text: str) -> int:
    # 只做表达方式统计，不推断人格、年龄、性别等敏感信息。
    return int(bool(re.search(
        r"[😂🤣🥲🥹😭😅😆😋😒😑🙃🙂☺️🥰😍😘😡🤔👀💀]|"
        r"[:;=xX][\-^']?[)(DPp]|"
        r"[（(][^\n]{0,8}[）)]",
        text,
    )))


async def observe_message(
    *,
    person_id: int,
    platform: str,
    chat_id,
    text: str,
    is_reply: bool = False,
):
    text = str(text or "").strip()
    if not text:
        return

    await init_profile_observer_db()

    chars = len(text)
    questions = int(any(x in text for x in ("?", "？", "吗", "么", "怎么", "为什么", "啥", "哪")))
    mentions = int("@" in text)
    emoji_like = _emoji_like(text)
    short = int(chars <= 8)
    long_ = int(chars >= 60)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO person_style_stats (
                person_id, platform, chat_id,
                message_count, total_chars, question_count,
                emoji_like_count, mention_count, reply_count,
                short_count, long_count, last_message_at
            )
            VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(person_id, platform, chat_id)
            DO UPDATE SET
                message_count=message_count+1,
                total_chars=total_chars+excluded.total_chars,
                question_count=question_count+excluded.question_count,
                emoji_like_count=emoji_like_count+excluded.emoji_like_count,
                mention_count=mention_count+excluded.mention_count,
                reply_count=reply_count+excluded.reply_count,
                short_count=short_count+excluded.short_count,
                long_count=long_count+excluded.long_count,
                last_message_at=excluded.last_message_at
            """,
            (
                int(person_id),
                str(platform),
                str(chat_id),
                chars,
                questions,
                emoji_like,
                mentions,
                int(bool(is_reply)),
                short,
                long_,
                now(),
            ),
        )
        await db.commit()


async def get_style_summary(
    *,
    person_id: int,
    platform: str,
    chat_id,
):
    await init_profile_observer_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                message_count, total_chars, question_count,
                emoji_like_count, mention_count, reply_count,
                short_count, long_count
            FROM person_style_stats
            WHERE person_id=? AND platform=? AND chat_id=?
            """,
            (
                int(person_id),
                str(platform),
                str(chat_id),
            ),
        )
        row = await cur.fetchone()

    if not row:
        return "还没有足够的聊天风格统计。"

    (
        count,
        total_chars,
        question_count,
        emoji_count,
        mention_count,
        reply_count,
        short_count,
        long_count,
    ) = row

    if count < 4:
        return f"目前只观察到 {count} 条真实消息，风格样本还少。"

    avg = total_chars / max(1, count)
    q_rate = question_count / max(1, count)
    reply_rate = reply_count / max(1, count)
    emoji_rate = emoji_count / max(1, count)
    short_rate = short_count / max(1, count)

    traits = []

    if avg <= 10 or short_rate >= 0.55:
        traits.append("平时发言偏短")
    elif avg >= 45:
        traits.append("平时会发比较完整的长句")
    else:
        traits.append("发言长度中等")

    if q_rate >= 0.30:
        traits.append("经常直接提问")

    if reply_rate >= 0.35:
        traits.append("比较常用回复链和别人接话")

    if emoji_rate >= 0.22:
        traits.append("聊天里表情/颜文字出现得比较多")

    if not traits:
        traits.append("目前没有特别明显的稳定表达习惯")

    return "；".join(traits) + f"。样本 {count} 条。"
