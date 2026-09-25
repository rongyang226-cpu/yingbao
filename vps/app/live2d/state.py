from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH
from app.activity.life_state import get_life_state
from app.activity.domestic import get_wardrobe_state
from app.activity.world_state import get_presence
from app.social.state import get_emotion_state


def _clamp(value, low=0.0, high=1.0):
    try:
        value = float(value)
    except Exception:
        value = 0.0
    return max(low, min(high, value))


async def _owner_person_id():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT person_id FROM people WHERE role='OWNER' ORDER BY person_id LIMIT 1"
        )
        row = await cur.fetchone()
    return int(row[0]) if row else None
def _expression_for(mood: str, *, sleeping: bool):
    if sleeping:
        return "sleepy"

    text = str(mood or "neutral").lower()
    mapping = (
        (("shy", "embarrass", "害羞", "脸红"), "shy"),
        (("sad", "hurt", "委屈", "难过"), "sad"),
        (("angry", "annoy", "生气", "不满"), "annoyed"),
        (("happy", "joy", "开心", "高兴"), "soft_smile"),
        (("tired", "sleepy", "困", "疲"), "sleepy"),
        (("surprise", "惊讶"), "surprised"),
        (("proud", "得意"), "proud"),
    )
    for needles, name in mapping:
        if any(x in text for x in needles):
            return name
    return "neutral"


def _normalized_valence(value):
    try:
        value = float(value)
    except Exception:
        return 0.0
    if value > 1.0 or value < -1.0:
        value = value / 100.0
    return max(-1.0, min(1.0, value))
async def build_live2d_state():
    life = await get_life_state()
    wardrobe = await get_wardrobe_state()
    presence = await get_presence()

    owner_id = await _owner_person_id()
    emotion = {
        "mood": "neutral",
        "valence": 0.0,
        "arousal": 0.0,
        "intensity": 0.0,
    }
    if owner_id is not None:
        try:
            emotion = await get_emotion_state(owner_id)
        except Exception:
            pass

    sleeping = life.get("sleep_state") == "sleeping"
    mood = emotion.get("mood") or "neutral"
    expression = _expression_for(mood, sleeping=sleeping)
    valence = _normalized_valence(emotion.get("valence"))
    energy = _clamp(life.get("energy", 0.5))
    eye_open = 0.08 if sleeping else (0.72 + energy * 0.24)
    mouth_form = valence * 0.55
    blush = 0.32 if expression == "shy" else 0.0

    params = {
        "ParamEyeLOpen": round(_clamp(eye_open), 3),
        "ParamEyeROpen": round(_clamp(eye_open), 3),
        "ParamMouthOpenY": 0.0,
        "ParamMouthForm": round(mouth_form, 3),
        "ParamBreath": 0.25 if sleeping else 0.42,
        "ParamCheek": blush,
        "ParamAngleX": 0.0,
        "ParamAngleY": 0.0,
        "ParamAngleZ": 0.0,
        "ParamEyeBallX": 0.0,
        "ParamEyeBallY": -0.08 if sleeping else 0.0,
    }

    activity = life.get("activity") or "idle"
    motion = "sleep_idle" if sleeping else f"{activity}_idle"

    return {
        "schema": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "expression": expression,
        "motion": motion,
        "parameters": params,
        "life": {
            "activity": activity,
            "sleep_state": life.get("sleep_state"),
            "energy": life.get("energy"),
        },
        "world": {
            "place": presence.get("place_key"),
        },
        "wardrobe": {
            "outfit_key": wardrobe.get("outfit_key"),
            "outfit_desc": wardrobe.get("outfit_desc"),
            "reason": wardrobe.get("reason"),
        },
        "emotion": {
            "mood": mood,
            "valence": emotion.get("valence"),
            "arousal": emotion.get("arousal"),
            "intensity": emotion.get("intensity"),
        },
    }
