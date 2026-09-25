import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from app.router.intent import (
    Intent,
    detect_intent,
)

from app.memory.query import (
    find_recent_message_db,
    list_recent_messages_db,
)

from app.memory.search import (
    search_messages_cn,
)

from app.tools.weather_tool import get_weather_for_place, format_weather_reply
from app.tools.web_search_tool import web_search


@dataclass
class RouteResult:
    intent: Intent

    # 是否已经得到确定答案
    handled: bool = False

    # 程序层确定答案
    answer: Optional[str] = None

    # 提供给后续模型的真实数据
    data: Any = None


async def dispatch(
    *,
    text: str,
    person_id: int,
    current_chat_id,
    platform: str,
    restrict_chat_id=None,
    current_message_id=None,
) -> RouteResult:

    intent = detect_intent(text)

    # ===== 空消息 =====
    if intent.type == "empty":
        return RouteResult(
            intent=intent,
            handled=True,
            answer=None,
        )

    # ===== 联网搜索 =====
    if intent.type == "web_search":
        try:
            result = await asyncio.wait_for(
                web_search(
                    intent.query,
                    limit=5,
                ),
                timeout=35.0,
            )
        except asyncio.TimeoutError:
            result = {
                "query": intent.query,
                "backend": "timeout",
                "results": [],
                "fallback_used": False,
                "error": "search_timeout",
            }
        except Exception as exc:
            result = {
                "query": intent.query,
                "backend": "error",
                "results": [],
                "fallback_used": False,
                "error": "search_failed",
                "error_detail": str(exc)[:240],
            }

        return RouteResult(
            intent=intent,
            handled=False,
            data=result,
        )

    if intent.type == "weather_missing_place":
        return RouteResult(intent=intent, handled=True, answer="想查哪个城市的天气？比如北京或东京。")

    # ===== 天气：用查到的数据直接作答，避免模型反说“查不到” =====
    if intent.type == "weather":
        try:
            result = await asyncio.wait_for(get_weather_for_place(intent.query), timeout=25)
        except Exception:
            return RouteResult(
                intent=intent, handled=True,
                answer=f"{intent.query}的天气服务暂时连接不上，这次没有实时数据。稍后再查。",
            )
        if not result:
            return RouteResult(
                intent=intent, handled=True,
                answer=f"没找到「{intent.query}」对应的地点。可以换成城市名再问我。",
            )
        return RouteResult(
            intent=intent, handled=True,
            answer=format_weather_reply(result, intent.target or "today"),
        )

    # ===== 最近消息查询 =====
    if intent.type == "recent_message":

        # 群聊中禁止跨场景查询私聊历史。
        safe_target = (
            "group"
            if restrict_chat_id is not None
            else intent.target
        )

        item = await find_recent_message_db(
            person_id=person_id,
            source=safe_target,
            current_chat_id=restrict_chat_id,
            platform=platform,
            exclude_message_id=current_message_id,
        )

        if item:
            if safe_target == "group":
                label = "群里"
            else:
                label = "私聊"

            return RouteResult(
                intent=intent,
                handled=True,
                answer=(
                    f"你刚才在{label}说的是："
                    f"{item['content']}"
                ),
                data=item,
            )

        return RouteResult(
            intent=intent,
            handled=True,
            answer="我这里没有找到对应的最近聊天记录。",
        )

    # ===== 指定场景历史 =====
    if intent.type == "history_messages":

        # 群聊中禁止跨场景查询私聊历史。
        safe_target = (
            "group"
            if restrict_chat_id is not None
            else intent.target
        )

        messages = await list_recent_messages_db(
            person_id=person_id,
            source=safe_target,
            current_chat_id=restrict_chat_id,
            platform=platform,
            exclude_message_id=current_message_id,
            limit=8,
        )

        if not messages:
            return RouteResult(
                intent=intent,
                handled=True,
                answer="我这里没有找到对应的聊天记录。",
            )

        label = (
            "群里"
            if safe_target == "group"
            else "私聊"
        )

        # 数据库决定内容，程序直接回答。
        lines = [
            f"{i + 1}. {item['content']}"
            for i, item in enumerate(
                reversed(messages)
            )
        ]

        return RouteResult(
            intent=intent,
            handled=True,
            answer=(
                f"你最近在{label}说过：\n"
                + "\n".join(lines)
            ),
            data=messages,
        )

    # ===== 主题历史回忆 =====
    if intent.type == "history_recall":

        memories = await search_messages_cn(
            person_id=person_id,
            query=text,
            platform=platform,
            chat_id=restrict_chat_id,
            limit=8,
        )

        # 搜索层只提供真实历史证据。
        # 最终自然语言交给模型组织。
        return RouteResult(
            intent=intent,
            handled=False,
            data=memories,
        )

    # ===== 普通聊天 =====
    return RouteResult(
        intent=intent,
        handled=False,
    )
