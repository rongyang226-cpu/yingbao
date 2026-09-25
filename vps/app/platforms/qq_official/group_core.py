from __future__ import annotations

import app.platforms.qq.bot as legacy


LEGACY_OWNER_ID = "913565158"


async def run_group_message(
    *,
    group_id: str,
    user_id: str,
    display_name: str | None,
    text: str,
    message_id: str | None,
    mentioned_bot: bool = False,
    replied_to_bot: bool = False,
    replied_message_id: str | None = None,
    reply_to_user_id: str | None = None,
    reply_to_name: str | None = None,
    mentions_other: bool = False,
    bridge_cooldown: bool = False,
    is_owner: bool = False,
):
    """
    官方 QQ 群消息 -> 现有猫猫群聊核心。

    官方 OpenID 作为普通群友身份键。
    OWNER 在进入旧核心时映射回原来的数字 QQ 身份，
    从而继续使用 person_id=1 和原有主人关系。
    """

    captured = {
        "reply": None,
    }

    async def capture_group_message(ws, target_group_id, reply):
        if reply:
            captured["reply"] = str(reply)

    async def no_member_target(*args, **kwargs):
        # 官方 QQ 的 @成员 后面单独实现。
        # 现在禁止调用旧 NapCat 的群成员/@逻辑。
        return None

    old_send_group = legacy.send_group_message
    old_resolve_member = legacy.resolve_group_member

    try:
        legacy.send_group_message = capture_group_message
        legacy.resolve_group_member = no_member_target

        internal_user_id = (
            LEGACY_OWNER_ID
            if is_owner
            else str(user_id)
        )

        nickname = (
            "洛小灵"
            if is_owner
            else (display_name or "群友")
        )

        msg = {
            "group_id": str(group_id),
            "user_id": internal_user_id,
            "nickname": nickname,
            "text": str(text or "").strip(),
            "message_id": message_id,
            "mentioned_bot": bool(mentioned_bot),
            "replied_to_bot": bool(replied_to_bot),
            "replied_message_id": replied_message_id,
            "reply_to_user_id": reply_to_user_id,
            "reply_to_name": reply_to_name,
            "mentions_other": bool(mentions_other),
            "bridge_cooldown": bool(bridge_cooldown),
        }

        await legacy.handle_qq_group(None, msg)

        return captured["reply"]

    finally:
        legacy.send_group_message = old_send_group
        legacy.resolve_group_member = old_resolve_member
