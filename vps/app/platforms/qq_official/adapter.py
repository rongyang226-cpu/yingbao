from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class OfficialQQMessage:
    chat_type: str
    chat_id: str
    user_id: str
    display_name: Optional[str]
    text: str
    message_id: Optional[str]
    mentioned_bot: bool = False
    replied_to_bot: bool = False


def _pick(obj: Any, *names: str):
    """
    同时兼容 dict / SDK 对象。
    """
    if obj is None:
        return None

    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)

        if value is not None:
            return value

    return None


def _extract_sender_name(msg: Any) -> Optional[str]:
    """
    名字优先级：
    1. SDK 标准化 senderName
    2. sender.name / sender.nickname / sender.username
    3. author.name / author.nickname / author.username
    4. raw.author.username
    """
    direct = _pick(msg, "senderName", "sender_name")
    if direct:
        return str(direct).strip() or None

    sender = _pick(msg, "sender")
    value = _pick(
        sender,
        "name",
        "nickname",
        "username",
        "displayName",
        "display_name",
    )
    if value:
        return str(value).strip() or None

    author = _pick(msg, "author")
    value = _pick(
        author,
        "name",
        "nickname",
        "username",
        "displayName",
        "display_name",
    )
    if value:
        return str(value).strip() or None

    raw = _pick(msg, "raw")
    raw_author = _pick(raw, "author")
    value = _pick(
        raw_author,
        "username",
        "nickname",
        "name",
    )
    if value:
        return str(value).strip() or None

    return None


def normalize_official_message(msg: Any) -> OfficialQQMessage:
    """
    把腾讯官方 QQ Bot SDK 消息统一成猫猫内部格式。

    OpenID 只作为底层身份键，不当作聊天昵称。
    """
    content = str(_pick(msg, "content") or "").strip()

    reply_target = _pick(msg, "replyTarget", "reply_target") or {}

    scope = str(_pick(reply_target, "scope") or "").lower()
    target_id = _pick(reply_target, "targetId", "target_id")
    message_id = (
        _pick(msg, "id", "messageId", "message_id")
        or _pick(reply_target, "msgId", "msg_id")
    )

    sender_id = _pick(
        msg,
        "senderId",
        "sender_id",
        "openid",
        "userOpenid",
        "user_openid",
    )

    sender = _pick(msg, "sender")
    author = _pick(msg, "author")

    if not sender_id:
        sender_id = _pick(
            sender,
            "id",
            "openid",
            "userOpenid",
            "user_openid",
        )

    if not sender_id:
        sender_id = _pick(
            author,
            "id",
            "openid",
            "userOpenid",
            "user_openid",
        )

    raw = _pick(msg, "raw")
    if not sender_id and raw:
        raw_author = _pick(raw, "author")
        sender_id = _pick(
            raw_author,
            "id",
            "openid",
            "user_openid",
        )

    # C2C 事件里，replyTarget.targetId 通常就是当前用户 openid
    if not sender_id and scope == "c2c":
        sender_id = target_id

    if not sender_id:
        raise ValueError("official QQ message has no sender openid")

    if scope == "group":
        chat_type = "group"
        chat_id = str(target_id or "")
    else:
        chat_type = "private"
        chat_id = str(sender_id)

    display_name = _extract_sender_name(msg)

    return OfficialQQMessage(
        chat_type=chat_type,
        chat_id=chat_id,
        user_id=str(sender_id),
        display_name=display_name,
        text=content,
        message_id=str(message_id) if message_id else None,
        mentioned_bot=bool(
            _pick(msg, "mentionedBot", "mentioned_bot")
        ),
        replied_to_bot=bool(
            _pick(msg, "repliedToBot", "replied_to_bot")
        ),
    )
