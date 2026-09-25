import asyncio
import json
import sys

from app.platforms.qq_official.owner_core import run_owner_private


async def main():
    raw = sys.stdin.read()
    data = json.loads(raw)

    text = str(data.get("text") or "").strip()
    message_id = data.get("message_id")

    if not text:
        print(json.dumps({"reply": ""}, ensure_ascii=False))
        return

    reply = await run_owner_private(
        text=text,
        message_id=message_id,
    )

    print(
        json.dumps(
            {"reply": reply or ""},
            ensure_ascii=False,
        )
    )


asyncio.run(main())
