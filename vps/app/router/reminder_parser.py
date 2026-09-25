import re
from typing import Optional

from app.tools.time_parser import parse_time
from app.tools.cn_number import parse_cn_number


REMINDER_WORDS = (
    "提醒我",
    "记得提醒我",
    "到时候提醒我",
    "叫我",
    "喊我",
    "记得叫我",
)


def is_reminder_request(text: str) -> bool:
    """
    只拦截具有明确提醒意图的消息。

    “提醒我/记得提醒我”本身就是明确提醒意图，
    可以进入多轮补全时间。

    “叫我/喊我”在中文里歧义很大：
    “可以叫我阿阳”“以后叫我哥哥”都不是提醒。
    因此只有同时出现明确时间表达时才按提醒处理。
    """
    if not text:
        return False

    text = text.strip()

    explicit_words = (
        "提醒我",
        "记得提醒我",
        "到时候提醒我",
    )
    if any(word in text for word in explicit_words):
        return True

    ambiguous_words = (
        "叫我",
        "喊我",
        "记得叫我",
    )
    if not any(word in text for word in ambiguous_words):
        return False

    time_patterns = (
        r"\d+\s*分钟(?:后|之后|以后)",
        r"半小时(?:后|之后|以后)?",
        r"\d+\s*小时(?:后|之后|以后)",
        r"\d+\s*天后",
        r"(?:今天|明天|后天|今晚|明晚|早上|上午|中午|下午|晚上|凌晨)",
        r"\d{1,2}\s*(?:点|[:：])",
        r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?",
    )

    return any(
        re.search(pattern, text)
        for pattern in time_patterns
    )


def _extract_title(text: str) -> str:
    """
    从提醒语句中尽量提取真正要提醒的内容。
    """

    result = text.strip()

    # 去掉对萤的称呼，只把它当作呼唤，不进入提醒正文。
    # 支持：
    # 萤，5分钟后提醒我喝水
    # 莹 5分钟后提醒我喝水
    # @萤 5分钟后提醒我喝水
    result = re.sub(
        r"^(?:@?萤|@?莹)\s*[，,。.!！?？:：\s]*",
        "",
        result,
        flags=re.I,
    )

    # 去提醒意图词
    for word in sorted(
        REMINDER_WORDS,
        key=len,
        reverse=True,
    ):
        result = result.replace(word, " ")

    # 去常见时间表达
    patterns = [
        r"\d+\s*分钟(?:后|之后|以后)",
        r"半小时(?:后|之后|以后)",
        r"\d+\s*小时(?:后|之后|以后)",
        r"\d+\s*天后",

        r"(?:今天|明天|后天|今晚|明晚)?"
        r"(?:上午|下午|晚上|早上|凌晨|中午)?"
        r"\s*\d{1,2}\s*点"
        r"(?:\s*\d{1,2}\s*分?)?"
        r"(?:半)?",

        r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?"
        r"(?:上午|下午|晚上|早上|凌晨|中午)?"
        r"\s*\d{1,2}\s*点"
        r"(?:\s*\d{1,2}\s*分?)?"
        r"(?:半)?",
    ]

    for pattern in patterns:
        result = re.sub(
            pattern,
            " ",
            result,
        )

    # 清理语气和标点
    result = re.sub(
        r"[，,。.!！?？]+",
        " ",
        result,
    )

    result = re.sub(
        r"\s+",
        " ",
        result,
    ).strip()

    return result


def _has_precise_time(text: str) -> bool:
    """
    判断提醒时间是否足够精确。

    “明天提醒我”不算精确；
    “明天下午3点”算。
    """

    if re.search(
        r"(?:\d+\s*分钟后|半小时后|\d+\s*小时后)",
        text,
    ):
        return True

    if re.search(
        r"\d{1,2}\s*(?:点|[:：])",
        text,
    ):
        return True

    return False



def _normalize_reminder_time(text: str) -> str:
    """
    仅在 reminder 场景中标准化口语时间。

    一分钟后 -> 1分钟后
    一分钟之后 -> 1分钟后
    一分钟提醒我 -> 1分钟后提醒我
    两小时之后 -> 2小时后
    半小时提醒我 -> 半小时后提醒我
    """
    result = text

    number_pattern = (
        r"(零|〇|一|二|两|三|四|五|六|七|八|九|"
        r"十|十一|十二|十三|十四|十五|十六|十七|十八|十九|"
        r"二十|二十一|二十二|二十三|二十四|二十五|二十六|"
        r"二十七|二十八|二十九|三十|"
        r"\d+)"
    )

    def convert(match):
        raw = match.group(1)
        unit = match.group(2)

        value = parse_cn_number(raw)

        if value is None:
            return match.group(0)

        return f"{value}{unit}后"

    # 中文/数字 + 分钟/小时 + 后/之后
    result = re.sub(
        number_pattern + r"\s*(分钟|小时)\s*(?:之后|以后|后)",
        convert,
        result,
    )

    # reminder 场景允许省略“后”
    # 例如：一分钟提醒我测试
    def convert_implicit(match):
        raw = match.group(1)
        unit = match.group(2)

        value = parse_cn_number(raw)

        if value is None:
            return match.group(0)

        return f"{value}{unit}后"

    result = re.sub(
        number_pattern
        + r"\s*(分钟|小时)(?=\s*(?:提醒我|叫我|喊我|记得))",
        convert_implicit,
        result,
    )

    # 半小时之后 / 半小时提醒我
    result = re.sub(
        r"半小时\s*(?:之后|以后|后)",
        "半小时后",
        result,
    )

    result = re.sub(
        r"半小时(?=\s*(?:提醒我|叫我|喊我|记得))",
        "半小时后",
        result,
    )

    # 中文钟点标准化：八点 -> 8点，晚上八点 -> 晚上8点
    def convert_clock(match):
        raw = match.group(1)
        value = parse_cn_number(raw)
        if value is None:
            return match.group(0)
        return f"{value}点"

    result = re.sub(
        number_pattern + r"\s*点",
        convert_clock,
        result,
    )

    return result


def parse_reminder_request(
    text: str,
) -> Optional[dict]:

    # ===== 排除“讨论已有提醒”的句子 =====
    # 这些是在询问/质疑提醒状态，不是在创建新提醒。
    reminder_query_patterns = (
        "为什么没提醒",
        "为什么没有提醒",
        "为什么不提醒",
        "怎么没提醒",
        "怎么没有提醒",
        "怎么不提醒",
        "刚才没提醒",
        "刚才没有提醒",
        "还没提醒",
        "没提醒我",
        "没有提醒我",
        "提醒了吗",
        "提醒了没",
        "提醒了没有",
        "我的提醒呢",
        "提醒呢",
    )

    if any(
        pattern in text
        for pattern in reminder_query_patterns
    ):
        return None

    # 先标准化中文时间，再判断“叫我/喊我”是不是提醒。
    # 否则“一分钟之后叫我”会因为还没转成数字而漏掉。
    text = _normalize_reminder_time(text)

    if not is_reminder_request(text):
        return None

    parsed_time = parse_time(text)

    if parsed_time is None:
        return {
            "ok": False,
            "reason": "missing_time",
            "title": _extract_title(text),
        }

    if not _has_precise_time(text):
        return {
            "ok": False,
            "reason": "imprecise_time",
            "title": _extract_title(text),
        }

    title = _extract_title(text)

    call_style = (
        "叫我" in text
        or "喊我" in text
        or "记得叫我" in text
    )

    if call_style and title in ("", "一下", "一声"):
        title = "叫你一下"

    if not title:
        return {
            "ok": False,
            "reason": "missing_title",
        }

    return {
        "ok": True,
        "title": title,
        "local_due_at": parsed_time["local_iso"],
        "due_at": parsed_time["utc_iso"],
        "timezone": parsed_time["timezone"],
    }
