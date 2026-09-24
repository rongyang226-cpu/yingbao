from __future__ import annotations

from pathlib import Path
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.config import TELEGRAM_OWNER_ID
from app.db import save_message, get_history
from app.brain.deepseek import chat as deepseek_chat
from app.router.dispatcher import dispatch
from app.context.builder import build_context, render_context
from app.social.state_engine import register_interaction
from app.social.interaction_events import apply_interaction_signals
from app.memory.extractor import extract_memory_candidates
from app.context.topic_tracker import observe_topic
from app.activity.attention import focus_on_conversation
from app.activity.life_state import get_life_state
from app.live2d.mobile_event_log import record_event

PERSONA_FILE = Path("/opt/ying/persona/core.md")
log = logging.getLogger(__name__)


async def _post_reply_memory(*, person_id, text, chat_id, message_id):
    try:
        # Memory extraction uses a second LLM request; defer it until after the visible reply.
        pass
    except Exception:
        log.exception("mobile deferred memory extraction failed")


def _chat_id(person_id: int) -> str:
    return f"mobile:{int(person_id)}"


async def _next_message_id() -> str:
    now = datetime.now(timezone.utc)
    return "mobile-" + now.strftime("%Y%m%d%H%M%S%f")


async def mobile_chat(text: str, person: dict) -> dict:
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "error": "empty_message"}

    person_id = int(person["person_id"])
    display_name = person.get("display_name") or "新朋友"
    role = str(person.get("person_role") or person.get("role") or "USER")
    chat_id = _chat_id(person_id)
    message_id = await _next_message_id()

    await save_message(
        "mobile", chat_id, str(person_id),
        display_name, "user", text,
        person_id=person_id, message_id=message_id,
    )

    try:
        life = await get_life_state()
        await focus_on_conversation(
            person_id=person_id,
            chat_id=chat_id,
            current_activity=life.get("activity") or "idle",
        )
    except Exception as exc:
        record_event("聊天错误", "同步萤的专注状态失败，已继续处理消息", error=exc)

    try:
        await register_interaction(
            person_id=person_id,
            source_platform="mobile",
            source_chat_id=chat_id,
            source_message_id=message_id,
        )
        await apply_interaction_signals(
            person_id=person_id, role=role,
            platform="mobile", chat_id=chat_id,
            source_message_id=message_id, text=text,
        )
        await observe_topic(
            person_id=person_id, platform="mobile",
            chat_id=chat_id, text=text,
        )
        await extract_memory_candidates(
            person_id, text, platform="mobile",
            chat_id=chat_id, message_id=message_id,
        )
    except Exception as exc:
        record_event("聊天错误", "更新互动、话题或记忆失败，已继续回复", error=exc)

    history = await get_history("mobile", chat_id, 20)
    route = await dispatch(
        text=text,
        person_id=person_id,
        current_chat_id=chat_id,
        platform="mobile",
        current_message_id=message_id,
    )

    if route.handled and route.answer is not None:
        answer = str(route.answer).strip()
    else:
        system_prompt = PERSONA_FILE.read_text(encoding="utf-8").strip()
        ctx_chat_id = (
            str(TELEGRAM_OWNER_ID)
            if role == "OWNER" and TELEGRAM_OWNER_ID
            else chat_id
        )
        runtime_context = await build_context(
            person={
                "person_id": person_id,
                "display_name": display_name,
                "role": role,
            },
            chat_id=ctx_chat_id,
            chat_type="private",
            user_id=ctx_chat_id,
            display_name=display_name,
            limit_recent=12,
        )
        system_prompt += "\n\n" + render_context(runtime_context)
        now_cn = datetime.now(timezone(timedelta(hours=8)))
        system_prompt += (f"\n\n【当前真实时间】\n- 北京时间/Asia/Shanghai：{now_cn.strftime('%Y-%m-%d %H:%M:%S')}。\n" "- 所有时间判断必须以这个时间为准，不得根据模型自身时间猜测。\n")
        system_prompt += (
            "\n\n【当前入口：莹宝手机端】\n"
            "- 这是与 Telegram 共用同一核心能力的手机入口。\n"
            "- 当前人物身份由 VPS 设备绑定决定，不要把不同人物混在一起。\n"
            "- OWNER 沿用既有人物与关系；其他人物从各自真实互动逐步建立画像。\n"
            "- 日常回复自然、简洁，不解释内部数据库或权限实现。"
        )
        if route.data:
            system_prompt += "\n\n【程序工具结果】\n" + str(route.data)[:7000]
        answer = await deepseek_chat(system_prompt, history, text, max_tokens=500)
        answer = str(answer or "").strip()

    reply_id = await _next_message_id()
    await save_message(
        "mobile", chat_id, "ying", "萤", "assistant", answer,
        person_id=person_id, message_id=reply_id,
    )
    # Reply is ready now; slow long-term-memory extraction continues in the background.
    asyncio.create_task(_post_reply_memory(
        person_id=person_id, text=text, chat_id=chat_id, message_id=message_id
    ))
    return {"ok": True, "reply": answer, "message_id": reply_id}
