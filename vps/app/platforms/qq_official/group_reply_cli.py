import asyncio
import json
import sys

from app.platforms.qq_official.group_core import run_group_message


async def main():
    data = json.loads(sys.stdin.read())

    reply = await run_group_message(
        group_id=str(data.get("group_id") or ""),
        user_id=str(data.get("user_id") or ""),
        display_name=data.get("display_name"),
        text=str(data.get("text") or ""),
        message_id=data.get("message_id"),
        mentioned_bot=bool(data.get("mentioned_bot")),
        replied_to_bot=bool(data.get("replied_to_bot")),
        is_owner=bool(data.get("is_owner")),
    )

    print(json.dumps(
        {"reply": reply or ""},
        ensure_ascii=False,
    ))


asyncio.run(main())
