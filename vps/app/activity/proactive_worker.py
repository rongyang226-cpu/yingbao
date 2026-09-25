import random
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite

from app.config import DB_PATH, TELEGRAM_OWNER_ID
from app.activity.life_state import get_life_state, update_life_state
from app.activity.needs import get_needs, set_needs
from app.activity.home_world import get_home_world
from app.activity.world_state import get_presence
from app.social.people import get_or_create_person, get_person_by_identity
from app.context.builder import build_context, render_context
from app.brain.deepseek import chat as deepseek_chat

TOKYO_TZ = ZoneInfo("Asia/Tokyo")
PERSONA_FILE = Path("/opt/ying/persona/core.md")

MIN_GAP_HOURS = 4.0
RECENT_CHAT_SILENCE_MINUTES = 70
DAILY_MAX = 3


def utcnow():
    return datetime.now(timezone.utc)


async def _init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS proactive_contact_state (
            local_date TEXT PRIMARY KEY,
            sent_count INTEGER NOT NULL DEFAULT 0,
            last_sent_at TEXT
        );
        """)
        await db.commit()


async def _last_owner_private_message():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT created_at
            FROM messages
            WHERE platform='telegram'
              AND user_id=?
              AND role='user'
              AND CAST(chat_id AS TEXT) NOT LIKE '-%'
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(TELEGRAM_OWNER_ID),),
        )
        row = await cur.fetchone()

    if not row or not row[0]:
        return None

    try:
        dt = datetime.fromisoformat(row[0])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def _today_state():
    await _init_db()
    today = datetime.now(TOKYO_TZ).date().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO proactive_contact_state
            (local_date, sent_count, last_sent_at)
            VALUES (?, 0, NULL)
            """,
            (today,),
        )
        cur = await db.execute(
            """
            SELECT sent_count, last_sent_at
            FROM proactive_contact_state
            WHERE local_date=?
            """,
            (today,),
        )
        row = await cur.fetchone()
        await db.commit()

    return today, int(row[0] or 0), row[1]


async def _mark_sent(today):
    t = utcnow().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE proactive_contact_state
            SET sent_count=sent_count+1,
                last_sent_at=?
            WHERE local_date=?
            """,
            (t, today),
        )
        await db.commit()

    await update_life_state(
        last_proactive_at=t
    )


def _hours_since(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(
            0.0,
            (utcnow() - dt.astimezone(timezone.utc)).total_seconds() / 3600,
        )
    except Exception:
        return None


async def proactive_tick(context):
    """
    萤自主联系 OWNER。
    - 睡着绝不发；
    - OWNER 刚聊过不机械追着发；
    - 每天最多 3 次；
    - 至少相隔 4 小时；
    - 概率受社交欲、沉默时长、时间段影响。
    """
    life = await get_life_state()

    if life.get("sleep_state") == "sleeping":
        return

    now_tokyo = datetime.now(TOKYO_TZ)
    hour = now_tokyo.hour

    # 深夜进入困倦流程后不主动刷消息。
    if hour < 7 or hour >= 1 and hour < 7:
        return

    today, sent_count, last_sent_at = await _today_state()

    if sent_count >= DAILY_MAX:
        return

    gap = _hours_since(last_sent_at or life.get("last_proactive_at"))
    if gap is not None and gap < MIN_GAP_HOURS:
        return

    last_user = await _last_owner_private_message()
    silence_minutes = None

    if last_user is not None:
        silence_minutes = max(
            0.0,
            (utcnow() - last_user).total_seconds() / 60,
        )

        if silence_minutes < RECENT_CHAT_SILENCE_MINUTES:
            return

    social = float(life.get("social_desire") or 0.5)
    try:
        needs = await get_needs()
        social_need = float(needs.get("social_need") or 0.0)
    except Exception:
        social_need = 0.0

    chance = 0.025
    chance += max(0.0, social - 0.50) * 0.20
    chance += max(0.0, social_need - 0.50) * 0.10

    if silence_minutes is not None:
        if silence_minutes >= 360:
            chance += 0.055
        elif silence_minutes >= 180:
            chance += 0.030

    if 20 <= hour <= 23:
        chance += 0.018
    elif 8 <= hour <= 11:
        chance += 0.010

    # 很困时可以偶尔发一条，但明显降低频率。
    if life.get("sleep_state") in {
        "sleepy",
        "in_bed",
        "trying_to_sleep",
        "restless",
    }:
        chance *= 0.35

    if random.random() >= min(chance, 0.14):
        return

    person = await get_person_by_identity(
        "telegram",
        TELEGRAM_OWNER_ID,
    )

    if person is None:
        person = await get_or_create_person(
            platform="telegram",
            user_id=TELEGRAM_OWNER_ID,
            username=None,
            display_name=None,
        )

    ctx = await build_context(
        person=person,
        chat_id=TELEGRAM_OWNER_ID,
        chat_type="private",
        user_id=TELEGRAM_OWNER_ID,
        display_name=person.get("display_name") or "OWNER",
        limit_recent=8,
    )

    system_prompt = PERSONA_FILE.read_text(encoding="utf-8")
    system_prompt += "\n\n" + render_context(ctx)
    system_prompt += """

【主动联系模式】
- 这是萤自己想起 OWNER 后主动发的一条即时消息，不是回复某条新消息。
- 只发 1～2 句，像真人突然想到对方。
- 可以从当前真实生活状态、情绪、天气、刚发生过的真实活动自然引出。
- 不得编造没有记录的经历。
- 不要解释为什么系统让你主动联系。
- 不要用“温馨提醒”“主人您好”“我来主动联系你了”之类机器人话术。
- 不要每次都说想念；可以只是随口说一句、吐槽、分享状态或问一句。
"""

    prompt = (
        "现在给 OWNER 发一条自然的主动消息。"
        "只输出要发送的聊天正文。"
    )

    try:
        answer = await deepseek_chat(
            system_prompt,
            [],
            prompt,
            max_tokens=100,
        )
    except Exception:
        return

    answer = str(answer or "").strip()
    if not answer:
        return

    # 防止意外长篇。
    if len(answer) > 220:
        answer = answer[:220].rstrip()

    await context.bot.send_message(
        chat_id=int(TELEGRAM_OWNER_ID),
        text=answer,
    )

    await _mark_sent(today)

    # 主动联系本身会轻微满足社交需求，但不会清零。
    try:
        needs = await get_needs()
        await set_needs(
            social_need=float(needs.get("social_need") or 0.0) - 0.16
        )
    except Exception:
        pass
