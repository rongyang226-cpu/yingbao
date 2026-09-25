from dataclasses import dataclass
from typing import Optional

from app.memory.recall import (
    should_recall,
    extract_recall_query,
)


@dataclass
class Intent:
    type: str
    query: Optional[str] = None
    target: Optional[str] = None
    confidence: float = 1.0


def _normalize(text: str) -> str:
    return (
        (text or "")
        .replace("？", "")
        .replace("?", "")
        .replace("。", "")
        .strip()
    )


def _asks_what_said(text: str) -> bool:
    patterns = (
        "说了什么",
        "说了啥",
        "说什么",
        "说过什么",
        "说过啥",
        "说过哪些",
        "发了什么",
        "发了啥",
        "发过什么",
        "发过啥",
        "聊了什么",
        "聊过什么",
        "聊过啥",
    )

    return any(x in text for x in patterns)


def _asks_history_location(text: str) -> bool:
    """
    识别“我之前/刚才在哪里说过某件事”这类跨场景回忆。
    这里只决定是否需要查历史，不决定答案。
    """
    location_words = (
        "在哪里说",
        "在哪说",
        "哪里说",
        "在哪儿说",
        "在哪里提",
        "在哪提",
        "哪里提",
        "在哪儿提",
        "在哪里聊",
        "在哪聊",
        "哪里聊",
        "在哪儿聊",
        "哪个群说",
        "哪个聊天说",
    )

    memory_words = (
        "刚刚",
        "刚才",
        "之前",
        "以前",
        "说过",
        "提过",
        "聊过",
        "记得",
        "知道",
    )

    return (
        any(x in text for x in location_words)
        and any(x in text for x in memory_words)
    )




def _is_weather_meta_chat(text: str) -> bool:
    """
    判断用户是在讨论“天气功能本身”，而不是真的查询天气。
    """
    t = _normalize(text)

    meta_phrases = (
        "给你加了",
        "给你加个",
        "给你加一个",
        "我给你加",
        "刚给你加",
        "天气功能",
        "天气系统",
        "天气模块",
        "世界天气功能",
        "全球天气功能",
        "接入天气",
        "加了天气",
        "支持天气",
        "天气能力",
        "天气api",
        "天气接口",
        "可以查别的地方",
        "能查别的地方",
        "可以查其他地方",
        "能查其他地方",
        "可以查全国",
        "能查全国",
        "可以查国外",
        "能查国外",
        "只能查东京",
        "只能查郑州",
        "只能查东京和郑州",
        "只能查东京、郑州",
    )

    return any(x in t.lower() for x in meta_phrases)


def _extract_weather_place(text: str):
    t = _normalize(text)

    if "天气" not in t and "温度" not in t and "下雨" not in t:
        return None

    if any(x in t for x in ("你那边", "你那里", "东京")):
        return "东京"

    if any(x in t for x in ("我这边", "我这里", "郑州")):
        return "郑州"

    cleaned = t

    remove_words = (
        "帮我查一下",
        "帮我查查",
        "帮我看看",
        "查一下",
        "查查",
        "查询一下",
        "查询",
        "看一下",
        "看看",
        "联网查一下",
        "联网查",
        "网上查一下",
        "网上查",
        "你能查一下",
        "你能查",
        "你可以查一下",
        "你可以查",
        "能不能查一下",
        "能不能查",
        "可以查一下",
        "可以查",
        "天气怎么样",
        "天气如何",
        "天气",
        "现在",
        "今天",
        "明天",
        "后天",
        "温度多少",
        "多少度",
        "会下雨吗",
        "下雨吗",
        "怎么样",
        "如何",
        "呢",
        "啊",
        "呀",
    )

    for word in remove_words:
        cleaned = cleaned.replace(word, "")

    cleaned = cleaned.strip(" ，,。！？!?")
    cleaned = cleaned.rstrip("吗嘛呢呀啊").strip()

    if cleaned:
        return cleaned

    return None


def _weather_day(text: str):
    t = _normalize(text)

    if "明天" in t:
        return "tomorrow"

    return "today"




def _extract_web_search_query(text: str):
    t = _normalize(text)

    # 必须有明确“去网上查”的意图，避免普通问题每次都联网。
    triggers = (
        "联网搜", "联网查", "网上搜", "网上查",
        "搜索一下", "搜一下", "搜搜看", "帮我搜",
        "查一下最新", "帮我查最新", "查查最新",
        "上网查", "上网搜",
    )

    matched = None
    for trigger in triggers:
        if trigger in t:
            matched = trigger
            break

    if not matched:
        return None

    query = t.replace(matched, "", 1).strip(" ，,。！？!?：:")
    query = query.replace("帮我", "", 1).strip()
    query = query.removeprefix("一下").strip()
    query = query.removeprefix("一下子").strip()

    return query or None


def detect_intent(text: str) -> Intent:
    """
    确定性第一层路由。

    不负责回答，只识别用户想查什么。
    """

    text = _normalize(text)

    if not text:
        return Intent(type="empty")

    # ===== 天气 =====
    # 先区分“讨论天气功能”和“真的查询天气”。
    # 例如“我给你加了世界天气感觉怎么样”应当继续普通聊天，
    # 不能因为出现“天气”“怎么样”就直接调用天气工具。
    if not _is_weather_meta_chat(text):
        weather_place = _extract_weather_place(text)

        if weather_place:
            return Intent(
                type="weather",
                query=weather_place,
                target=_weather_day(text),
                confidence=0.99,
            )


    # ===== 明确联网搜索 / 明确最新信息 =====
    web_query = _extract_web_search_query(text)

    if not web_query and any(
        x in text
        for x in (
            "最新消息",
            "最新新闻",
            "今天新闻",
            "今日新闻",
            "最近发生",
            "刚刚发生",
        )
    ):
        web_query = text

    if web_query:
        return Intent(
            type="web_search",
            query=web_query,
            confidence=0.99,
        )

    asks_said = _asks_what_said(text)

    recent_words = (
        "刚刚",
        "刚才",
        "上一句",
        "上句话",
        "最近",
    )

    is_recent = any(
        x in text for x in recent_words
    )

    # ===== 群聊消息查询 =====
    if asks_said and "群" in text:

        # 明确问“刚才” → 最近一条
        if is_recent:
            return Intent(
                type="recent_message",
                target="group",
                confidence=1.0,
            )

        # “我在群里说过啥” → 查群聊历史
        return Intent(
            type="history_messages",
            target="group",
            query=text,
            confidence=1.0,
        )

    # ===== 私聊消息查询 =====
    if asks_said and "私聊" in text:

        if is_recent:
            return Intent(
                type="recent_message",
                target="private",
                confidence=1.0,
            )

        return Intent(
            type="history_messages",
            target="private",
            query=text,
            confidence=1.0,
        )

    # ===== 跨场景历史位置查询 =====
    if _asks_history_location(text):
        query = extract_recall_query(text) or text
        return Intent(
            type="history_recall",
            query=query,
            confidence=0.98,
        )

    # ===== 普通历史回忆 =====
    if should_recall(text):
        query = extract_recall_query(text)

        if query:
            return Intent(
                type="history_recall",
                query=query,
                confidence=0.95,
            )

    return Intent(
        type="chat",
        confidence=1.0,
    )
