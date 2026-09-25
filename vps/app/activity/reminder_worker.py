import html
import json
import logging

from app.memory.events import (
    get_due_events,
    claim_event,
    release_event,
    complete_event,
)
from app.social.state_engine import apply_emotion_event
from app.social.bond_engine import apply_bond_event

log = logging.getLogger(__name__)


async def reminder_tick(context):
    """
    到期提醒：
    - 群聊：@ 原始发起者
    - 私聊：正常提醒
    - 旧提醒没有 details 时继续兼容
    """
    events = await get_due_events(limit=20)

    if not events:
        return

    for event in events:
        event_id = event["id"]

        try:
            claimed = await claim_event(event_id)

            if not claimed:
                continue

            if event.get("source_platform") != "telegram":
                await release_event(event_id)
                continue

            chat_id = event.get("source_chat_id")

            if not chat_id:
                log.warning(
                    "Reminder %s has no source_chat_id",
                    event_id,
                )
                await release_event(event_id)
                continue

            title = (
                event.get("title")
                or "你之前让我提醒你的事"
            ).strip()

            details = {}
            raw_details = event.get("details")

            if raw_details:
                try:
                    details = json.loads(raw_details)
                except Exception:
                    details = {}

            target_user_id = str(
                details.get("target_user_id") or ""
            )

            target_name = str(
                details.get("target_name") or ""
            ).strip()

            is_group = bool(
                details.get("is_group")
            )

            if (
                is_group
                and target_user_id
            ):
                # Telegram HTML mention，不依赖 username。
                safe_name = html.escape(
                    target_name
                    or "你"
                )

                text = (
                    f'<a href="tg://user?id={target_user_id}">'
                    f'{safe_name}</a> '
                    f'到时间了，{title}。'
                )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                )

            elif is_group:
                # 匿名管理员没有可可靠点击的个人 tg://user id。
                # 至少使用按群隔离后的签名名，不把提醒错发成别人的 @。
                prefix = (
                    f"{target_name} "
                    if target_name
                    else ""
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{prefix}到时间了，{title}。",
                )

            else:
                # 私聊或旧提醒兼容。
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"到时间了，{title}。",
                )

            await complete_event(event_id)

            # 成功兑现一个真实提醒，作为“承诺完成”的轻量关系事件。
            person_id = event.get("person_id")
            if person_id is not None:
                try:
                    await apply_emotion_event(
                        person_id=int(person_id),
                        event_type="expectation_fulfilled",
                        reason="reminder_delivered",
                    )
                    await apply_bond_event(
                        person_id=int(person_id),
                        event_type="expectation_fulfilled",
                        source_platform="telegram",
                        source_chat_id=chat_id,
                        source_message_id=event.get("source_message_id"),
                    )
                except Exception:
                    log.exception(
                        "Reminder relationship event failed event_id=%s",
                        event_id,
                    )

            log.info(
                "Reminder delivered event_id=%s chat_id=%s target=%s",
                event_id,
                chat_id,
                target_user_id or "-",
            )

        except Exception:
            try:
                await release_event(event_id)
            except Exception:
                log.exception(
                    "Failed to release reminder claim event_id=%s",
                    event_id,
                )

            log.exception(
                "Reminder delivery failed event_id=%s",
                event_id,
            )
