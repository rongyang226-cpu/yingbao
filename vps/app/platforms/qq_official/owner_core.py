from __future__ import annotations

import json

# 直接复用现有猫猫私聊核心
from app.platforms.qq.bot import handle_qq_private


LEGACY_OWNER_ID = "913565158"


class CaptureWS:
    """
    假 WebSocket：
    不连接 NapCat，只截获猫猫旧核心生成的 send_private_msg。
    """

    def __init__(self):
        self.reply = None

    async def send(self, payload):
        data = json.loads(payload)

        if data.get("action") != "send_private_msg":
            return

        params = data.get("params") or {}
        message = params.get("message")

        if message:
            self.reply = str(message)


async def run_owner_private(
    *,
    text: str,
    message_id: str | None,
):
    ws = CaptureWS()

    msg = {
        # 官方身份已在外层验证。
        # 进入旧核心后映射为猫猫原来的 OWNER 身份，
        # 从而完整继承原记忆/权限/关系。
        "user_id": LEGACY_OWNER_ID,
        "nickname": "洛小灵",
        "text": text,
        "message_id": message_id,
    }

    await handle_qq_private(ws, msg)

    return ws.reply
