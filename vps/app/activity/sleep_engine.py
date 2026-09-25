SLEEP_TRANSITIONS = {
    "awake": {"sleepy"},
    "sleepy": {"awake", "in_bed"},
    "in_bed": {"awake", "trying_to_sleep"},
    "trying_to_sleep": {"restless", "sleeping"},
    "restless": {"trying_to_sleep", "sleeping", "awake"},
    "sleeping": {"awake"},
}


def can_transition(current: str, target: str) -> bool:
    return target in SLEEP_TRANSITIONS.get(current, set())


RESTLESS_REASONS = {
    "overthinking",
    "emotional_residue",
    "anxious",
    "afraid",
    "not_tired",
    "unknown",
}


def normalize_restless_reason(reason: str) -> str:
    if reason in RESTLESS_REASONS:
        return reason
    return "unknown"


def clamp_distress(value):
    return max(0.0, min(1.0, float(value)))


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.social.state import now
from app.social.state_engine import get_current_emotion
from app.activity.life_state import (
    get_life_state,
    update_life_state,
    get_or_create_daily_cycle,
    get_daily_phase,
)
from app.activity.home_world import update_home_world
from app.activity.world_state import set_presence
from app.activity.domestic import update_outfit


async def transition_sleep(target: str, reason=None, distress=None):
    current = await get_life_state()
    source = current["sleep_state"]

    if not can_transition(source, target):
        raise ValueError(
            f"invalid sleep transition: {source} -> {target}"
        )

    changes = {
        "sleep_state": target,
    }

    if target == "trying_to_sleep":
        changes["sleep_attempt_at"] = now()
        changes["restless_reason"] = None
        changes["distress"] = 0.0

    elif target == "restless":
        changes["restless_reason"] = normalize_restless_reason(
            reason or "unknown"
        )
        changes["distress"] = clamp_distress(
            0.25 if distress is None else distress
        )

    elif target == "sleeping":
        changes["last_sleep_at"] = now()
        changes["restless_reason"] = None
        changes["distress"] = 0.0
        changes["activity"] = "sleeping"

    elif target == "awake":
        changes["last_wake_at"] = now()
        changes["restless_reason"] = None
        changes["distress"] = 0.0
        changes["sleep_attempt_at"] = None

        # 真正从睡眠中醒来时，同步结束 sleeping 活动。
        # 不覆盖已经由其他活动引擎设置的新活动。
        if source != "awake" and current["activity"] == "sleeping":
            changes["activity"] = "idle"

    updated = await update_life_state(**changes)

    # 睡眠状态属于强地点约束：真正睡着时必须在主卧，
    # 避免 life_state / home_world / world_presence 三套状态分叉。
    if target == "sleeping":
        await update_home_world(
            room_location="bedroom",
            light_state="off",
            clear_game=True,
        )
        await set_presence(
            "bedroom",
            reason="sleep:sleeping",
        )
        await update_outfit(
            activity="sleeping",
            sleep_state="sleeping",
        )
    elif target == "awake" and source == "sleeping":
        # 刚醒时仍然先在主卧，不瞬移到客厅。
        await update_home_world(
            room_location="bedroom",
            clear_game=True,
        )
        await set_presence(
            "bedroom",
            reason="sleep:awake",
        )
        await update_outfit(
            activity="idle",
            sleep_state="awake",
        )

    return updated


import random


def decide_sleep_outcome(
    *,
    energy,
    arousal,
    sleep_difficulty,
    negative_emotion=0.0,
):
    energy = clamp_distress(energy)
    arousal = clamp_distress(arousal)
    sleep_difficulty = clamp_distress(sleep_difficulty)
    negative_emotion = clamp_distress(negative_emotion)

    restlessness = (
        sleep_difficulty * 0.35
        + arousal * 0.30
        + negative_emotion * 0.20
        + energy * 0.15
    )

    restlessness += random.uniform(-0.12, 0.12)
    restlessness = clamp_distress(restlessness)

    if restlessness < 0.38:
        return {
            "outcome": "sleep",
            "restlessness": restlessness,
            "reason": None,
        }

    reason_weights = {
        "overthinking": arousal + 0.15,
        "emotional_residue": negative_emotion + 0.10,
        "anxious": (arousal + negative_emotion) / 2 + 0.10,
        "afraid": negative_emotion * 0.45 + arousal * 0.20,
        "not_tired": energy + 0.05,
    }

    reason = max(
        reason_weights,
        key=reason_weights.get,
    )

    return {
        "outcome": "restless",
        "restlessness": restlessness,
        "reason": reason,
    }


def suggest_sleep_transition(
    *,
    phase,
    current_sleep_state,
):
    if phase in ("sleeping", "sleep_window"):
        if current_sleep_state == "awake":
            return "sleepy"
        if current_sleep_state == "sleepy":
            return "in_bed"
        if current_sleep_state == "in_bed":
            return "trying_to_sleep"
        return None

    if phase == "active":
        if current_sleep_state == "sleeping":
            return "awake"
        return None

    if phase == "evening":
        if current_sleep_state == "awake":
            return "sleepy"
        return None

    if phase == "sleepy":
        if current_sleep_state == "awake":
            return "sleepy"
        if current_sleep_state == "sleepy":
            return "in_bed"
        return None

    return None


async def sleep_tick(
    *,
    emotion_person_id=None,
    current_time=None,
):
    tz = ZoneInfo("Asia/Shanghai")

    if current_time is None:
        current_time = datetime.now(tz)
    elif current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=tz)
    else:
        current_time = current_time.astimezone(tz)

    life = await get_life_state()

    cycle = await get_or_create_daily_cycle(
        current_time.date().isoformat()
    )

    phase = get_daily_phase(
        cycle,
        current_time,
    )

    state = life["sleep_state"]

    # 已经在尝试入睡：判断睡着还是失眠
    if state == "trying_to_sleep":
        arousal = 0.0
        negative_emotion = 0.0

        if emotion_person_id is not None:
            emotion = await get_current_emotion(
                emotion_person_id
            )
            arousal = max(
                0.0,
                float(emotion["arousal"]),
            )
            negative_emotion = max(
                0.0,
                -float(emotion["valence"]),
            )

        sleep_cycle = cycle

        # 凌晨仍在入睡流程时，
        # 入睡困难倾向应属于前一天晚上
        if current_time.hour < 6:
            previous_date = (
                current_time.date()
                - timedelta(days=1)
            ).isoformat()

            sleep_cycle = await get_or_create_daily_cycle(
                previous_date
            )

        decision = decide_sleep_outcome(
            energy=life["energy"],
            arousal=arousal,
            sleep_difficulty=sleep_cycle[
                "sleep_difficulty"
            ],
            negative_emotion=negative_emotion,
        )

        if decision["outcome"] == "sleep":
            new_state = await transition_sleep(
                "sleeping"
            )

            return {
                "action": "fell_asleep",
                "phase": phase,
                "decision": decision,
                "state": new_state,
            }

        new_state = await transition_sleep(
            "restless",
            reason=decision["reason"],
            distress=decision["restlessness"],
        )

        return {
            "action": "became_restless",
            "phase": phase,
            "decision": decision,
            "state": new_state,
        }

    # 失眠后不会永远卡住：
    # 下一轮重新尝试入睡
    if state == "restless":
        new_state = await transition_sleep(
            "trying_to_sleep"
        )

        return {
            "action": "retry_sleep",
            "phase": phase,
            "state": new_state,
        }

    target = suggest_sleep_transition(
        phase=phase,
        current_sleep_state=state,
    )

    if target is None:
        return {
            "action": "no_change",
            "phase": phase,
            "state": life,
        }

    new_state = await transition_sleep(target)

    return {
        "action": f"{state}_to_{target}",
        "phase": phase,
        "state": new_state,
    }
