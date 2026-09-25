from __future__ import annotations

import random

from app.activity.life_state import get_life_state
from app.activity.needs import get_needs


def _pick(items):
    return random.choice(tuple(items))


async def ambient_bubble() -> str | None:
    life = await get_life_state()
    needs = await get_needs()

    if life.get("sleep_state") == "sleeping":
        return None

    activity = str(life.get("activity") or "idle")
    boredom = float(needs.get("boredom") or 0.0)

    if boredom >= 0.72:
        return _pick((
            "有点无聊……",
            "唔，好像没什么事做。",
            "要不要找点东西玩……",
            "今天安静得有点过头了。",
        ))
    phrases = {
        "reading": ("这段还挺有意思。", "再看一会儿。"),
        "gaming": ("刚刚差一点。", "这局还没结束呢。"),
        "listening": ("这首还不错。", "嗯……继续听。"),
        "phone": ("又刷了一会儿。", "好像也没看到什么特别的。"),
        "walking": ("外面空气还行。", "慢慢走一会儿。"),
        "eating": ("先让我吃完。", "这个味道还不错。"),
        "washing": ("等一下，我还没弄完。",),
        "organizing": ("这里还差一点。", "收完就舒服了。"),
        "preparing_sleep": ("有点困了……", "差不多该睡了。"),
        "idle": ("嗯……", "在发呆。", "窗外挺安静的。"),
    }
    return _pick(phrases.get(activity, ("在呢。", "嗯……")))


async def poke_reaction(area: str = "body", streak: int = 1) -> str:
    life = await get_life_state()
    sleeping = life.get("sleep_state") == "sleeping"
    activity = str(life.get("activity") or "idle")
    area = str(area or "body").lower()
    streak = max(1, int(streak or 1))

    if sleeping:
        return _pick(("唔……别闹。", "……让我睡。", "嗯……？"))
    if streak >= 6:
        return _pick(("你还戳……", "差不多行了。", "很闲吗你。"))
    if streak >= 3:
        return _pick(("干嘛一直戳我。", "又来？", "我感觉到了啦。"))

    if area in {"head", "hair"}:
        return _pick(("嗯？", "别把头发弄乱。", "干嘛摸我头。"))
    if area in {"face", "cheek"}:
        return _pick(("脸也要戳？", "……痒。", "别闹。"))
    if area in {"hand", "arm"}:
        return _pick(("怎么了？", "嗯？", "拉我干嘛。"))
    if activity == "reading":
        return _pick(("等我看完这段。", "嗯？怎么了。"))
    if activity == "gaming":
        return _pick(("等下，打着呢。", "别害我操作失误。"))

    return _pick(("嗯？", "干嘛呀。", "我在。", "戳到了。"))
