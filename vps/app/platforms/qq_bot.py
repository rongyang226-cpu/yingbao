import asyncio
import json
import logging
import os

from websockets.asyncio.client import connect

log = logging.getLogger(__name__)


QQ_OWNER_ID = str(
    os.getenv("QQ_OWNER_ID", "")
).strip()

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
    把 OneBot 11 消息事件整理成萤核心容易理解的统一结构。
    暂时只做文本消息。
    """
    message_type = event.get("message_type")
    user_id = str(event.get("user_id") or "")
    group_id = event.get("group_id")
    message_id = str(event.get("message_id") or "")

    raw_message = event.get("raw_message") or ""

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
        "text": raw_message,
        "is_owner": is_owner,
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


async def handle_onebot_event(event: dict):
    """
    QQ 平台入口。
    下一步再把这里接到萤现有聊天核心。
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
    持续连接 NapCat OneBot 11 WebSocket。
    断线自动重连，不影响 Telegram 主程序。
    使用指数退避，避免短时间高频重连。
    """
    retry_seconds = 40

    while True:
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

                        if msg:
                            log.info(
                                "QQ text: user=%s group=%s text=%r",
                                msg["user_id"],
                                msg["group_id"],
                                msg["text"][:120],
                            )

                    except json.JSONDecodeError:
                        log.warning(
                            "QQ received invalid JSON"
                        )

                    except Exception:
                        log.exception(
                            "QQ event handling failed"
                        )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            log.warning(
                "QQ WebSocket disconnected: %s; retry in %ss",
                exc,
                retry_seconds,
            )

            await asyncio.sleep(40)
