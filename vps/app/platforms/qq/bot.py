from pathlib import Path
import asyncio
import json
import logging
import os
import random
import time

from websockets.asyncio.client import connect


from app.social.people import get_or_create_person
from app.social.address_memory import remember_preferred_address
from app.social.state_engine import register_interaction
from app.db import save_message
from app.platforms.qq.qq_builder import render_context

QQ_PERSONA_FILE = Path("/opt/ying/persona/qq_core.md")

def load_qq_persona():
    try:
        return QQ_PERSONA_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

from app.brain.deepseek import chat
from app.platforms.qq.qzone import (
    qzone_tick,
    build_qzone_post,
    publish_qzone_post,
    mark_qzone_posted,
)
from app.platforms.qq.group_members import resolve_group_member, send_group_at
from app.platforms.qq.permissions import (
    get_qq_role,
    set_qq_role,
    list_qq_roles,
    can_manage_permissions,
    can_manage_qzone,
    can_modify_memory,
    can_modify_settings,
    can_manage_core,
    ROLE_OWNER,
    ROLE_VIEWER,
    ROLE_NORMAL,
)
from app.platforms.qq.context import (
    build_qq_context,
    QQ_NATURAL_STYLE_RULES,
    QQ_PRIVATE_STYLE_RULES,
    QQ_PRIVATE_ANTI_AI_RULES,
    QQ_PRIVATE_HUMAN_V2_RULES,
)


from app.platforms.qq.social import (
    should_proactively_message,
    mark_proactive_sent,
    social_action_due,
    mark_social_action,
)
from app.db import DB_PATH
import aiosqlite
from datetime import datetime, timezone

log = logging.getLogger(__name__)

QQ_GROUP_LAST_REPLY = {}


QQ_OWNER_ID = "913565158"

QQ_ONEBOT_WS = os.getenv(
    "QQ_ONEBOT_WS",
    "ws://127.0.0.1:3001"
).strip()

QQ_ONEBOT_TOKEN = os.getenv(
    "QQ_ONEBOT_TOKEN",
    ""
).strip()


def normalize_qq_message(event: dict) -> dict:
    """
    把 OneBot 11 消息事件整理成猫猫核心容易理解的统一结构。
    暂时只做文本消息。
    """
    message_type = event.get("message_type")
    user_id = str(event.get("user_id") or "")
    group_id = event.get("group_id")
    message_id = str(event.get("message_id") or "")

    raw_message = event.get("raw_message") or ""
    message_segments = event.get("message") or []

    self_id = str(event.get("self_id") or "")
    mentioned_bot = False
    replied_message_id = None
    text_parts = []

    if isinstance(message_segments, list):
        for seg in message_segments:
            if not isinstance(seg, dict):
                continue

            seg_type = seg.get("type")
            data = seg.get("data") or {}

            if seg_type == "text":
                text_parts.append(
                    str(data.get("text") or "")
                )

            elif seg_type == "at":
                target = str(data.get("qq") or "")
                if target == self_id:
                    mentioned_bot = True

            elif seg_type == "reply":
                replied_message_id = str(
                    data.get("id") or ""
                ) or None

    clean_text = "".join(text_parts).strip()

    if not clean_text:
        clean_text = raw_message.strip()

    sender = event.get("sender") or {}

    nickname = (
        sender.get("card")
        or sender.get("nickname")
        or user_id
    )

    is_owner = bool(
        QQ_OWNER_ID
        and user_id == QQ_OWNER_ID
    )

    return {
        "platform": "qq",
        "message_type": message_type,
        "user_id": user_id,
        "group_id": str(group_id) if group_id else None,
        "message_id": message_id,
        "nickname": nickname,
        "text": clean_text,
        "is_owner": is_owner,
        "self_id": self_id,
        "mentioned_bot": mentioned_bot,
        "replied_message_id": replied_message_id,
        "replied_to_bot": bool(
            replied_message_id and mentioned_bot
        ),
        "raw": event,
    }


def is_message_event(event: dict) -> bool:
    return event.get("post_type") == "message"


def is_supported_message(event: dict) -> bool:
    if not is_message_event(event):
        return False

    return event.get("message_type") in {
        "private",
        "group",
    }


async def qq_owner_recently_active(minutes=90):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT created_at
            FROM messages
            WHERE platform='qq'
              AND chat_id=?
              AND user_id=?
              AND role='user'
            ORDER BY id DESC
            LIMIT 1
            """,
            (QQ_OWNER_ID, QQ_OWNER_ID),
        )

        row = await cur.fetchone()

    if not row or not row[0]:
        return False

    try:
        dt = datetime.fromisoformat(row[0])

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        age_minutes = (
            datetime.now(timezone.utc)
            - dt.astimezone(timezone.utc)
        ).total_seconds() / 60

        return age_minutes < minutes

    except Exception:
        return False


async def qq_proactive_tick(ws):
    try:
        if await qq_owner_recently_active(90):
            return

        should_send, meta = await should_proactively_message()

        if not should_send:
            return

        person = await get_or_create_person(
            platform="qq",
            user_id=QQ_OWNER_ID,
            username=None,
            display_name="洛小灵",
        )

        bundle = await build_qq_context(
            person=person,
            chat_id=QQ_OWNER_ID,
            chat_type="private",
            user_id=QQ_OWNER_ID,
            display_name="洛小灵",
            message_id=None,
            limit_recent=12,
        )

        ctx = bundle["context"]
        history = bundle["history"]

        system_prompt = load_qq_persona()
        if system_prompt:
            system_prompt += "\n\n"
        system_prompt += render_context(ctx)
        system_prompt += "\n\n" + QQ_NATURAL_STYLE_RULES


        system_prompt += (
            "\n\n【主动联系】\n"
            "现在是猫猫自己想起主人并主动发消息。"
            "只能基于当前真实生活状态和最近真实生活轨迹说话。"
            "不要假装主人刚发过消息。"
            "不要解释自己为什么会主动联系。"
            "回复自然、像真人，通常1到2句。"
        )

        prompt = (
            "根据你现在真实的生活状态，"
            "自然地主动给主人发一句消息。"
        )

        reply = await chat(
            system_prompt=system_prompt,
            history=history,
            user_text=prompt,
            max_tokens=120,
        )

        reply = ensure_cat_miao(reply)

        if not reply:
            return

        await send_private_message(
            ws,
            QQ_OWNER_ID,
            reply,
        )

        await save_message(
            "qq",
            QQ_OWNER_ID,
            "cat",
            "猫猫",
            "assistant",
            reply,
            person_id=None,
            message_id=None,
        )

        mark_proactive_sent()

        log.info(
            "QQ proactive message sent to OWNER"
        )

    except Exception:
        log.exception(
            "QQ proactive tick failed"
        )



async def send_qq_like(ws, user_id, times=1):
    await ws.send(
        json.dumps(
            {
                "action": "send_like",
                "params": {
                    "user_id": int(user_id),
                    "times": int(times),
                },
            },
            ensure_ascii=False,
        )
    )


async def send_qq_poke(ws, user_id):
    await ws.send(
        json.dumps(
            {
                "action": "friend_poke",
                "params": {
                    "user_id": int(user_id),
                },
            },
            ensure_ascii=False,
        )
    )


async def qq_social_action_tick(ws):
    """
    OWNER 专属低频 QQ 社交动作。
    不机械执行，只在冷却结束后小概率触发。
    """
    try:
        life = await get_life_state()

        sleep_state = str(
            life.get("sleep_state") or ""
        )

        activity = str(
            life.get("activity") or ""
        )

        if sleep_state in {
            "sleeping",
            "trying_to_sleep",
            "in_bed",
        }:
            return

        if activity == "preparing_sleep":
            return

        # 点赞：最低 72h 冷却，之后低概率想起来才点
        if social_action_due("like", 72):
            if random.random() < 0.04:
                await send_qq_like(
                    ws,
                    QQ_OWNER_ID,
                    times=1,
                )

                mark_social_action("like")

                log.info(
                    "QQ low-frequency like sent to OWNER"
                )

                # 一轮只做一种动作，避免行为过密
                return

        # 戳一戳：最低 48h 冷却，比点赞还低概率
        if social_action_due("poke", 48):
            if random.random() < 0.03:
                await send_qq_poke(
                    ws,
                    QQ_OWNER_ID,
                )

                mark_social_action("poke")

                log.info(
                    "QQ low-frequency poke sent to OWNER"
                )

    except Exception:
        log.exception(
            "QQ social action tick failed"
        )





async def handle_owner_permission_command(
    user_id,
    text,
):
    """
    OWNER 私聊权限管理。
    不是权限命令时返回 None。
    """
    import re

    if not can_manage_permissions(user_id):
        return None

    raw = (text or "").strip()

    # 查看权限详细说明
    if raw in {
        "权限详细",
        "权限详情",
        "权限说明",
        "详细权限",
        "权限分级",
        "权限等级说明",
    }:
        return (
            "QQ权限只有三级：\n"
            "OWNER：最高权限，仅洛洛拥有；可管理权限、发空间、修改核心数据。\n"
            "VIEWER：观察员/只读；可以查看允许的信息和正常聊天，但不能修改、授权或发空间。\n"
            "NORMAL：普通用户；只有普通聊天权限。\n"
            "不存在 ADMIN、MEMBER 之类的额外等级。"
        )

    # 查看自己的权限
    if raw in {
        "我的权限",
        "我什么权限",
        "我是什么权限",
        "我的等级",
        "权限等级",
    }:
        role = get_qq_role(user_id)

        if role == ROLE_OWNER:
            return "你是 OWNER，最高权限。"
        elif role == ROLE_VIEWER:
            return "你是观察员，只读权限。"
        else:
            return "你是普通用户。"

    # 查看全部授权
    if raw in {
        "查看权限",
        "观看权限",
        "权限列表",
        "看权限",
        "查看授权",
        "看授权",
        "查看权限列表",
    }:
        roles = list_qq_roles(user_id)

        if not roles:
            return "现在没有额外授权。"

        lines = []

        for uid, role in roles.items():
            if role == ROLE_OWNER:
                label = "OWNER"
            elif role == ROLE_VIEWER:
                label = "观察员"
            else:
                label = "普通"

            lines.append(
                f"{uid}：{label}"
            )

        return "\n".join(lines)

    # 授权 1401547848 观察员
    m = re.match(
        r"^授权\s*(\d{5,12})\s*(?:观察员|viewer|只读|查看)$",
        raw,
        flags=re.I,
    )

    if m:
        target = m.group(1)

        ok, result = set_qq_role(
            user_id,
            target,
            ROLE_VIEWER,
        )

        if not ok:
            return result

        return f"已把 {target} 设为观察员。"

    # 撤销权限 1401547848
    m = re.match(
        r"^(?:撤销权限|取消授权|移除权限|恢复普通)\s*(\d{5,12})$",
        raw,
    )

    if m:
        target = m.group(1)

        ok, result = set_qq_role(
            user_id,
            target,
            ROLE_NORMAL,
        )

        if not ok:
            return result

        return f"已撤销 {target} 的额外权限。"

    return None


async def handle_owner_qzone_command(
    user_id,
    text,
):
    """
    OWNER QQ 私聊控制空间。

    返回：
      None -> 不是空间命令
      str  -> 已处理，返回给 OWNER 的回复
    """
    if not can_manage_qzone(user_id):
        return None

    import re

    raw = (text or "").strip()

    # ---------- 指定正文直接发布 ----------
    patterns = [
        r"^(?:发空间|发个空间|发条空间|发说说|发条说说)\s*[：:]\s*(.+)$",
        r"^(?:空间发|说说发)\s*[：:]\s*(.+)$",
    ]

    for pattern in patterns:
        m = re.match(
            pattern,
            raw,
            flags=re.S,
        )

        if not m:
            continue

        content = m.group(1).strip()

        if not content:
            return "你还没告诉我要发什么。"

        ok = await publish_qzone_post(
            content
        )

        if not ok:
            return "没发出去，空间那边刚刚出了点问题。"

        mark_qzone_posted(
            content
        )

        log.info(
            "QQ QZone manual post published by OWNER"
        )

        return "发好了。"

    # ---------- 让猫猫自己生成 ----------
    normalized = raw.rstrip(
        "。.!！?？~～"
    ).strip()

    auto_patterns = [
        r"^(?:随便)?发(?:个|条|一条)?(?:空间|说说)(?:吧)?(?:，|,|\s)*(?:什么都可以|随便|你看着发|想发啥都行|想发什么都行)?$",
        r"^发点(?:什么|东西)(?:到|去)?(?:空间|说说)(?:吧)?$",
        r"^(?:你)?看着发(?:个|条)?(?:空间|说说)?(?:吧)?$",
    ]

    if not any(
        re.match(pattern, normalized)
        for pattern in auto_patterns
    ):
        return None

    content = await build_qzone_post()

    if not content:
        return "现在没什么特别想发的，先不发。"

    ok = await publish_qzone_post(
        content
    )

    if not ok:
        return "刚刚没发出去。"

    mark_qzone_posted(
        content
    )

    log.info(
        "QQ QZone generated post published by OWNER"
    )

    return "发好了。"


async def send_private_message(ws, user_id, text):
    payload = {
        "action": "send_private_msg",
        "params": {
            "user_id": int(user_id),
            "message": text,
        }
    }
    await ws.send(json.dumps(payload, ensure_ascii=False))


def ensure_cat_miao(text: str) -> str:
    """猫猫正常回复结尾加“喵”，单字符短回复除外。"""
    import re

    text = (text or "").strip()
    if not text:
        return ""

    # 已经自然以“喵”结尾，不重复添加
    if text.endswith("喵"):
        return text

    # 忽略句末标点后判断实际正文长度
    body = re.sub(r"[。.!！?？~～]+$", "", text).rstrip()

    # “嗯”“好”“行”“哦”等单字符回复保持自然
    if len(body) <= 1:
        return text

    if not body:
        return text

    return body + "喵"



def clean_qq_private_output(text: str) -> str:
    import re

    text = (text or "").strip()

    # 所有换行压成普通空格
    text = re.sub(r"\s*\n+\s*", " ", text)

    # 连续空白压成一个
    text = re.sub(r"[ \t]+", " ", text)

    # 中文标点前后不留机械空格
    text = re.sub(r"\s+([，。！？、；：…])", r"\1", text)
    text = re.sub(r"([，。！？、；：…])\s+", r"\1", text)

    return text.strip()



async def handle_qq_private(ws, msg):
    user_id = str(msg["user_id"])
    text = (msg.get("text") or "").strip()

    if not text:
        return

    display_name = (
        "洛小灵"
        if user_id == QQ_OWNER_ID
        else (msg.get("nickname") or user_id)
    )

    person = await get_or_create_person(
        platform="qq",
        user_id=user_id,
        username=None,
        display_name=display_name,
    )

    # QQ OWNER 必须映射到共享 OWNER
    if user_id == QQ_OWNER_ID and person.get("role") != "OWNER":
        log.error(
            "QQ owner identity mismatch: user=%s person=%s",
            user_id,
            person,
        )
        return

    # QQ 私聊自己的 chat_id 就是对方 QQ
    chat_id = user_id

    saved = await save_message(
        "qq",
        chat_id,
        user_id,
        msg.get("nickname") or user_id,
        "user",
        text,
        person_id=person["person_id"],
        message_id=msg.get("message_id"),
    )

    if not saved:
        return

    # OWNER 私聊权限管理。
    try:
        permission_reply = await handle_owner_permission_command(
            user_id,
            text,
        )
    except Exception:
        log.exception(
            "QQ OWNER permission command failed"
        )
        permission_reply = "权限操作刚刚出错了。"

    if permission_reply is not None:
        await send_private_message(
            ws,
            user_id,
            permission_reply,
        )

        await save_message(
            "qq",
            chat_id,
            "cat",
            "猫猫",
            "assistant",
            permission_reply,
            person_id=None,
            message_id=None,
        )

        return

    # OWNER 私聊可直接控制 QQ 空间。
    try:
        qzone_reply = await handle_owner_qzone_command(
            user_id,
            text,
        )
    except Exception:
        log.exception(
            "QQ OWNER QZone command failed"
        )
        qzone_reply = "空间这边刚刚出错了。"

    if qzone_reply is not None:
        await send_private_message(
            ws,
            user_id,
            qzone_reply,
        )

        await save_message(
            "qq",
            chat_id,
            "cat",
            "猫猫",
            "assistant",
            qzone_reply,
            person_id=None,
            message_id=None,
        )

        return

    # 只有 OWNER 可以通过 QQ 私聊修改长期资料。
    # VIEWER / NORMAL 只能聊天和查看，不能写入称呼或核心记忆。
    if can_modify_memory(user_id):
        try:
            await remember_preferred_address(
                person_id=person["person_id"],
                text=text,
                source_platform="qq",
                source_chat_id=chat_id,
                source_message_id=msg.get("message_id"),
            )
        except Exception:
            log.exception(
                "QQ preferred address memory failed"
            )

    bundle = await build_qq_context(
        person=person,
        chat_id=chat_id,
        chat_type="private",
        user_id=user_id,
        display_name=msg.get("nickname") or user_id,
        message_id=msg.get("message_id"),
        limit_recent=12,
    )

    ctx = bundle["context"]
    history = bundle["history"]

    system_prompt = load_qq_persona()
    if system_prompt:
        system_prompt += "\n\n"
    system_prompt += render_context(ctx)
    system_prompt += "\n\n" + QQ_NATURAL_STYLE_RULES
    system_prompt += "\n\n" + QQ_PRIVATE_STYLE_RULES
    system_prompt += "\n\n" + QQ_PRIVATE_ANTI_AI_RULES
    system_prompt += "\n\n" + QQ_PRIVATE_HUMAN_V2_RULES

    reply = await chat(
        system_prompt=system_prompt,
        history=history,
        user_text=text,
        max_tokens=90,
    )

    reply = clean_qq_private_output(reply)
    reply = ensure_cat_miao(reply)

    if not reply:
        return

    await send_private_message(
        ws,
        user_id,
        reply,
    )

    # QQ 自己保存 QQ 回复，不进入 Telegram 历史
    await save_message(
        "qq",
        chat_id,
        "cat",
        "猫猫",
        "assistant",
        reply,
        person_id=None,
        message_id=None,
    )



async def send_group_message(ws, group_id, text):
    payload = {
        "action": "send_group_msg",
        "params": {
            "group_id": int(group_id),
            "message": text,
        }
    }

    await ws.send(
        json.dumps(
            payload,
            ensure_ascii=False,
        )
    )


def should_reply_qq_group(msg):
    text = (msg.get("text") or "").strip()

    # 回复猫猫 / @猫猫 都必回
    if msg.get("replied_to_bot"):
        return True

    if msg.get("mentioned_bot"):
        return True

    # 明确叫名字必回
    normalized = text.lstrip("，,。.!！?？ ")

    if (
        normalized.startswith("猫猫")
    ):
        return True

    group_id = str(msg.get("group_id") or "")
    user_id = str(msg.get("user_id") or "")

    key = (group_id, user_id)
    now_ts = time.monotonic()

    last = QQ_GROUP_LAST_REPLY.get(key)

    # 普通参与：同一个人 60 秒冷却
    if last is not None and now_ts - last < 60:
        return False

    # 普通群聊 50% 概率参与
    if random.random() >= 0.30:
        return False

    QQ_GROUP_LAST_REPLY[key] = now_ts
    return True


async def handle_qq_group(ws, msg):
    group_id = str(msg["group_id"])
    user_id = str(msg["user_id"])
    text = (msg.get("text") or "").strip()

    if not text:
        return

    nickname = (
        msg.get("nickname")
        or user_id
    )

    identity_name = (
        "洛小灵"
        if user_id == QQ_OWNER_ID
        else nickname
    )

    person = await get_or_create_person(
        platform="qq",
        user_id=user_id,
        username=None,
        display_name=identity_name,
    )

    # 群里的 QQ OWNER 仍然必须是 OWNER
    if (
        user_id == QQ_OWNER_ID
        and person.get("role") != "OWNER"
    ):
        log.error(
            "QQ owner identity mismatch in group: "
            "user=%s person=%s",
            user_id,
            person,
        )
        return

    # 所有真实群消息先保存。
    # chat_id 使用 group_id，因此不会和私聊混在一起。
    saved = await save_message(
        "qq",
        group_id,
        user_id,
        nickname,
        "user",
        text,
        person_id=person["person_id"],
        message_id=msg.get("message_id"),
    )

    if not saved:
        return

    if not should_reply_qq_group(msg):
        return

    # QQ 群里只有明确“@/艾特/叫一下/喊一下某人”时，
    # 才尝试解析群成员并真正 @。
    try:
        target = await resolve_group_member(
            group_id,
            text,
        )
    except Exception:
        target = None
        log.exception(
            "QQ group member resolve failed"
        )

    if target:
        await send_group_at(
            ws,
            group_id,
            target["user_id"],
            text=f"{target['name']}，洛洛叫你一下。",
        )
        return

    bundle = await build_qq_context(
        person=person,
        chat_id=group_id,
        chat_type="group",
        user_id=user_id,
        display_name=nickname,
        message_id=msg.get("message_id"),
        limit_recent=20,
    )

    ctx = bundle["context"]
    history = bundle["history"]

    # 给模型明确当前发言者，避免群聊身份串人。
    ctx["qq_current_speaker"] = {
        "user_id": user_id,
        "display_name": nickname,
        "role": person.get("role"),
    }

    system_prompt = load_qq_persona()
    if system_prompt:
        system_prompt += "\n\n"
    system_prompt += render_context(ctx)
    system_prompt += "\n\n" + QQ_NATURAL_STYLE_RULES

    system_prompt += (
        "\\n\\n【QQ群聊当前发言者】\\n"
        f"QQ号：{user_id}\\n"
        f"名字：{nickname}\\n"
        f"身份：{'主人' if person.get('role') == 'OWNER' else '普通群友'}\\n"
        "当前消息的QQ号是最高优先级身份锚点。"
        "只能把当前消息归属于这个QQ号对应的人。"
        "不要继承上一条消息的说话人身份。"
        "不要因为昵称相似、称呼相同或连续发言而把两个人合并。"
        "历史中的QQ号只用于内部区分身份，回复时不要主动说出QQ号。"
        "913565158 永远是OWNER洛洛，其他QQ号绝不能当成洛洛。"
    )

    reply = await chat(
        system_prompt=system_prompt,
        history=history,
        user_text=text,
        max_tokens=160,
    )

    reply = ensure_cat_miao(reply)

    if not reply:
        return

    await send_group_message(
        ws,
        group_id,
        reply,
    )

    # 只有猫猫真正参与并成功回复后，
    # 才记录与当前群友的一次真实关系互动。
    try:
        await register_interaction(
            person_id=person["person_id"],
            source_platform="qq",
            source_chat_id=group_id,
            source_message_id=msg.get("message_id"),
        )
    except Exception:
        log.exception(
            "QQ group relationship interaction failed"
        )

    await save_message(
        "qq",
        group_id,
        "cat",
        "猫猫",
        "assistant",
        reply,
        person_id=None,
        message_id=None,
    )



async def handle_onebot_event(event: dict):
    """
    QQ 平台入口。
    QQ 猫猫聊天入口。
    """
    if not is_supported_message(event):
        return None

    msg = normalize_qq_message(event)

    log.info(
        "QQ message received: type=%s user=%s group=%s message_id=%s",
        msg["message_type"],
        msg["user_id"],
        msg["group_id"],
        msg["message_id"],
    )

    return msg



async def run_qq_listener():
    """
    QQ SAFE MODE listener.

    只建立一次 OneBot WebSocket 连接。
    连接断开后直接退出，不在程序内部自动重连。
    主动私聊、自动社交动作、自动 QZone 均保持关闭。
    """
    try:
        headers = None

        if QQ_ONEBOT_TOKEN:
            headers = {
                "Authorization": f"Bearer {QQ_ONEBOT_TOKEN}"
            }

        log.info(
            "Connecting QQ OneBot WebSocket: %s",
            QQ_ONEBOT_WS,
        )

        async with connect(
            QQ_ONEBOT_WS,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
            max_size=8 * 1024 * 1024,
        ) as ws:
            log.info("QQ OneBot WebSocket connected")

            # SAFE MODE:
            # 不创建任何主动行为后台任务。
            log.warning(
                "QQ SAFE MODE active: "
                "proactive/social/qzone disabled"
            )

            async for raw in ws:
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode(
                            "utf-8",
                            errors="replace",
                        )

                    event = json.loads(raw)

                    if not isinstance(event, dict):
                        continue

                    msg = await handle_onebot_event(event)

                    if not msg:
                        continue

                    log.info(
                        "QQ text: user=%s group=%s text=%r",
                        msg["user_id"],
                        msg["group_id"],
                        msg["text"][:120],
                    )

                    if msg["message_type"] == "private":
                        await handle_qq_private(ws, msg)

                    elif msg["message_type"] == "group":
                        await handle_qq_group(ws, msg)

                except json.JSONDecodeError:
                    log.warning(
                        "QQ received invalid JSON"
                    )

                except asyncio.CancelledError:
                    raise

                except Exception:
                    log.exception(
                        "QQ event handling failed"
                    )

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        log.warning(
            "QQ WebSocket disconnected: %s; "
            "SAFE MODE stops listener",
            exc,
        )
        return

    log.warning(
        "QQ WebSocket closed; "
        "SAFE MODE stops listener"
    )
