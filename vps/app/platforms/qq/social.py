import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.activity.life_state import get_life_state


STATE_FILE = Path("/opt/ying/data/qq_social_state.json")
TOKYO = ZoneInfo("Asia/Tokyo")

MIN_PROACTIVE_HOURS = 4


def _load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(
            STATE_FILE.read_text(encoding="utf-8")
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
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except Exception:
        return None


async def should_proactively_message():
    """
    只判断现在是否适合猫猫主动联系 OWNER。
    不负责生成或发送消息。
    """
    now = datetime.now(timezone.utc)
    tokyo_now = now.astimezone(TOKYO)

    # 深夜不主动打扰
    if tokyo_now.hour < 8:
        return False, None

    if (
        tokyo_now.hour == 23
        and tokyo_now.minute >= 30
    ):
        return False, None

    life = await get_life_state()

    sleep_state = str(
        life.get("sleep_state") or ""
    )

    activity = str(
        life.get("activity") or ""
    )

    social_desire = float(
        life.get("social_desire", 0.5)
    )

    if sleep_state in {
        "sleeping",
        "trying_to_sleep",
        "in_bed",
    }:
        return False, None

    if activity == "preparing_sleep":
        return False, None

    state = _load_state()

    last_at = _parse_time(
        state.get("last_proactive_at")
    )

    if last_at:
        if now - last_at < timedelta(
            hours=MIN_PROACTIVE_HOURS
        ):
            return False, None

    # 社交欲望低时基本不主动
    if social_desire < 0.55:
        return False, None

    chance = 0.05

    if social_desire >= 0.65:
        chance += 0.10

    if social_desire >= 0.80:
        chance += 0.10

    # 比较容易想起主人的生活状态
    if activity in {
        "phone",
        "dazing",
        "resting",
        "listening",
    }:
        chance += 0.08

    if activity == "gaming":
        chance += 0.04

    # 晚上更容易主动聊天
    if 19 <= tokyo_now.hour <= 22:
        chance += 0.08

    chance = min(chance, 0.35)

    if random.random() >= chance:
        return False, None

    return True, {
        "activity": activity,
        "social_desire": social_desire,
        "tokyo_time": tokyo_now.isoformat(),
    }


def mark_proactive_sent():
    state = _load_state()

    state["last_proactive_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    _save_state(state)


def social_action_due(action, min_hours):
    """
    判断某个 QQ 社交动作距离上次执行是否已经足够久。
    """
    state = _load_state()
    key = f"last_{action}_at"
    last_at = _parse_time(state.get(key))

    if not last_at:
        return True

    return (
        datetime.now(timezone.utc) - last_at
        >= timedelta(hours=min_hours)
    )


def mark_social_action(action):
    state = _load_state()

    state[f"last_{action}_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    _save_state(state)
