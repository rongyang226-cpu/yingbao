import json
import asyncio
import urllib.request
import urllib.error
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.activity.life_state import (
    get_life_state,
    get_recent_activity_history,
)
from app.activity.home_world import get_home_world
from app.platforms.qq.qq_builder import render_context

QQ_PERSONA_FILE = Path("/opt/ying/persona/qq_core.md")

def load_qq_persona():
    try:
        return QQ_PERSONA_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

from app.platforms.qq.context import build_qq_context
from app.social.people import get_or_create_person
from app.brain.deepseek import chat


QQ_OWNER_ID = "913565158"

STATE_FILE = Path(
    "/opt/ying/data/qq_qzone_state.json"
)

MIN_HOURS = 48
SOFT_HOURS = 72

QZONE_BRIDGE_URL = "http://127.0.0.1:5700/send_msg"
QZONE_BRIDGE_TOKEN = "ying_qzone_2026"


def _load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def _save_state(state):
    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _parse_time(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt

    except Exception:
        return None


def qzone_due():
    state = _load_state()

    last = _parse_time(
        state.get("last_post_at")
    )

    if not last:
        return True

    age = (
        datetime.now(timezone.utc)
        - last
    )

    if age < timedelta(hours=MIN_HOURS):
        return False

    if age >= timedelta(hours=SOFT_HOURS):
        return True

    # 48~72 小时之间随机决定，
    # 避免机械固定间隔。
    return random.random() < 0.35


def mark_qzone_posted(text):
    state = _load_state()

    state["last_post_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    state["last_post_text"] = text

    _save_state(state)


async def build_qzone_post():
    """
    只生成文案，不负责真正发布。
    """
    life = await get_life_state()

    if life.get("sleep_state") == "sleeping":
        return None

    history = await get_recent_activity_history(
        limit=8
    )

    if not history:
        return None

    world = await get_home_world()

    # 至少要有一点真实生活内容。
    meaningful = [
        item
        for item in history
        if item.get("activity")
        not in {
            None,
            "",
            "idle",
        }
    ]

    if not meaningful:
        return None

    person = await get_or_create_person(
        platform="qq",
        user_id=QQ_OWNER_ID,
        username=None,
        display_name="洛小灵",
    )

    bundle = await build_qq_context(
        person=person,
        chat_id=QQ_OWNER_ID,
        chat_type="private",
        user_id=QQ_OWNER_ID,
        display_name="洛小灵",
        message_id=None,
        limit_recent=8,
    )

    system_prompt = load_qq_persona()
    if system_prompt:
        system_prompt += "\n\n"

    system_prompt += render_context(
        bundle["context"]
    )

    real_activity_lines = []

    for item in meaningful[:5]:
        activity = item.get("activity")
        game = item.get("game_name")

        if activity == "gaming" and game:
            real_activity_lines.append(
                f"- 玩过《{game}》"
            )
        else:
            real_activity_lines.append(
                f"- {activity}"
            )

    facts = "\n".join(
        real_activity_lines
    )

    system_prompt += f"""

【QQ空间动态任务】

你准备以猫猫自己的身份发一条QQ空间动态。

只能根据下面真实发生的生活素材写：
{facts}

当前活动：
{life.get("activity")}

当前房间位置：
{world.get("room_location")}

严格要求：
- 不得编造外出、地点、照片、见面或现实经历。
- 不得提数据库、程序、状态机、模型、API。
- 不要像总结报告。
- 像真人随手发的QQ空间。
- 1到3句。
- 可以有一点情绪，但不要矫情。
- 如果这些素材根本不值得发，就输出：NO_POST
"""

    result = await chat(
        system_prompt=system_prompt,
        history=[],
        user_text=(
            "决定现在有没有值得发的动态。"
            "有的话直接写动态正文，"
            "没有就只输出 NO_POST。"
        ),
        max_tokens=120,
    )

    result = (result or "").strip()

    if not result:
        return None

    if result.upper() == "NO_POST":
        return None

    return result


async def publish_qzone_post(text):
    """
    真正发布 QQ 空间动态。
    只有 bridge 明确返回成功时才算成功。
    """
    text = (text or "").strip()
    if not text:
        return False

    def _send():
        payload = json.dumps(
            {"message": text},
            ensure_ascii=False,
        ).encode("utf-8")

        req = urllib.request.Request(
            QZONE_BRIDGE_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": (
                    f"Bearer {QZONE_BRIDGE_TOKEN}"
                ),
                "Content-Type": (
                    "application/json"
                ),
            },
        )

        try:
            with urllib.request.urlopen(
                req,
                timeout=20,
            ) as resp:
                raw = resp.read().decode(
                    "utf-8",
                    errors="replace",
                )
        except Exception:
            return False

        try:
            data = json.loads(raw)
        except Exception:
            return False

        return (
            data.get("status") == "ok"
            and data.get("retcode") == 0
        )

    return await asyncio.to_thread(_send)


async def qzone_tick():
    """
    一次自动空间检查：
    到时间 -> 判断是否值得发 -> 发布 ->
    只有成功发布才推进 2~3 天计时。
    """
    if not qzone_due():
        return False

    text = await build_qzone_post()
    if not text:
        return False

    ok = await publish_qzone_post(text)
    if not ok:
        return False

    mark_qzone_posted(text)
    return True
