import asyncio
import json
import re
import urllib.request


NAPCAT_HTTP = "http://127.0.0.1:3000"
NAPCAT_TOKEN = "ying_onebot_2026"


async def get_group_members(group_id):
    def _fetch():
        body = json.dumps({
            "group_id": int(group_id)
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{NAPCAT_HTTP}/get_group_member_list",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {NAPCAT_TOKEN}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(
                resp.read().decode("utf-8")
            )

        if data.get("status") != "ok":
            return []

        if data.get("retcode") != 0:
            return []

        return data.get("data") or []

    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
        return []


def _name(member):
    return str(
        member.get("card")
        or member.get("nickname")
        or ""
    ).strip()


def extract_target(text):
    text = (text or "").strip()

    # 去掉叫猫猫本人的称呼
    text = re.sub(
        r"^(?:猫猫)[，,。.!！?？\s]*",
        "",
        text,
    )

    patterns = [
        # @诗人 / 艾特诗人
        r"(?:@|艾特)\s*([^\s，。！？,.!?]{1,20})",

        # 把诗人叫出来 / 把诗人喊出来
        r"把\s*([^\s，。！？,.!?]{1,20}?)\s*(?:叫|喊)(?:出来|过来|来一下|一下)",

        # 叫诗人出来 / 喊诗人过来
        r"(?:叫|喊)\s*([^\s，。！？,.!?]{1,20}?)\s*(?:出来|过来|来一下|一下)",

        # 叫一下诗人 / 喊一下诗人
        r"(?:叫一下|叫下|喊一下|喊下)\s*([^\s，。！？,.!?]{1,20})",

        # 找诗人
        r"找\s*([^\s，。！？,.!?]{1,20})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            target = m.group(1).strip()

            # 去掉后面的口语内容
            target = re.split(
                r"(?:我|有事|有事情|一下|出来|过来)",
                target,
                maxsplit=1,
            )[0].strip()

            if target:
                return target

    return None


async def resolve_group_member(group_id, text):
    target = extract_target(text)

    if not target:
        return None

    members = await get_group_members(group_id)

    exact = []
    fuzzy = []

    for member in members:
        uid = str(member.get("user_id") or "")
        name = _name(member)

        if not uid or not name:
            continue

        if name == target:
            exact.append((uid, name))
        elif target in name:
            fuzzy.append((uid, name))

    matches = exact or fuzzy

    if len(matches) != 1:
        return None

    uid, name = matches[0]

    return {
        "user_id": uid,
        "name": name,
    }


async def send_group_at(ws, group_id, user_id, text="叫你一下。"):
    payload = {
        "action": "send_group_msg",
        "params": {
            "group_id": int(group_id),
            "message": [
                {
                    "type": "at",
                    "data": {
                        "qq": str(user_id)
                    },
                },
                {
                    "type": "text",
                    "data": {
                        "text": " " + text
                    },
                },
            ],
        },
    }

    await ws.send(
        json.dumps(
            payload,
            ensure_ascii=False,
        )
    )
