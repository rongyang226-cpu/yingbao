from app.memory.events import (
    get_open_events,
    cancel_event,
)


def is_list_reminders(text: str) -> bool:
    text = (text or "").strip()

    patterns = (
        "我的提醒",
        "有哪些提醒",
        "有什么提醒",
        "查看提醒",
        "看看提醒",
        "提醒列表",
    )

    return any(p in text for p in patterns)


def extract_cancel_title(text: str):
    text = (text or "").strip()

    prefixes = (
        "取消提醒我",
        "取消我的",
        "取消",
        "删除提醒我",
        "删除我的",
        "删除",
    )

    result = text

    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix):]
            break

    for suffix in (
        "的提醒",
        "提醒",
        "这个提醒",
    ):
        if result.endswith(suffix):
            result = result[:-len(suffix)]
            break

    result = result.strip(" ，,。.!！?？")

    return result or None


def is_cancel_reminder(text: str) -> bool:
    text = (text or "").strip()

    return (
        text.startswith("取消")
        or text.startswith("删除")
    ) and "提醒" in text


async def find_open_reminders(
    person_id: int,
):
    events = await get_open_events(
        person_id,
        limit=20,
    )

    return [
        e for e in events
        if e["type"] == "reminder"
    ]


async def cancel_reminder_by_title(
    person_id: int,
    title: str,
):
    reminders = await find_open_reminders(
        person_id
    )

    title = title.strip()

    # 优先完全匹配
    exact = [
        e for e in reminders
        if e["title"] == title
    ]

    if len(exact) == 1:
        event = exact[0]

        ok = await cancel_event(
            event["id"]
        )

        return {
            "ok": ok,
            "event": event,
            "ambiguous": False,
        }

    # 再做包含匹配
    matches = [
        e for e in reminders
        if (
            title in e["title"]
            or e["title"] in title
        )
    ]

    if len(matches) == 1:
        event = matches[0]

        ok = await cancel_event(
            event["id"]
        )

        return {
            "ok": ok,
            "event": event,
            "ambiguous": False,
        }

    if len(matches) > 1:
        return {
            "ok": False,
            "event": None,
            "ambiguous": True,
            "matches": matches,
        }

    return {
        "ok": False,
        "event": None,
        "ambiguous": False,
    }
