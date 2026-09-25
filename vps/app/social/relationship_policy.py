import random
import re

ROMANCE_REQUEST_PATTERNS = (
    r"做我(女朋友|老婆|对象|恋人)",
    r"当我(女朋友|老婆|对象|恋人)",
    r"(和我|跟我)(谈恋爱|交往|处对象|在一起)",
    r"(嫁给我|娶你|我们结婚)",
    r"(你是我老婆|你当我老婆|叫我老公)",
    r"(能不能|可以不可以|愿不愿意).{0,8}(和我在一起|做我女朋友|当我对象|谈恋爱)",
    r"(我喜欢你|我爱你).{0,12}(做我女朋友|和我在一起|当我对象|谈恋爱)",
)

FRIEND_ONLY_REPLIES = (
    "想得美。我现在只当你的猫娘搭档，喵。",
    "恋爱剧情已经收起来了。来，换个话题拌嘴，喵。",
    "别乱升级关系啦。朋友和搭档也能聊得很开心，喵。",
)


def is_romance_escalation(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False

    return any(
        re.search(pattern, raw, flags=re.I)
        for pattern in ROMANCE_REQUEST_PATTERNS
    )


def friend_only_reply() -> str:
    return random.choice(FRIEND_ONLY_REPLIES)


_ROMANCE_CONFIRM_PATTERNS = (
    r"(我是你(老婆|女朋友|对象|恋人))",
    r"(你是我(老公|男朋友|对象|恋人))",
    r"(我们(在一起了|谈恋爱吧|就是恋人|是情侣))",
    r"(以后叫我(老婆|女朋友|对象|恋人))",
    r"(可以叫我(老婆|女朋友|对象|恋人))",
    r"(我答应(做你女朋友|和你在一起|跟你谈恋爱))",
)


def enforce_friend_only_output(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return text

    for pattern in _ROMANCE_CONFIRM_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            return friend_only_reply()

    return text
