import random


ACTIVITIES = {
    "idle",
    "dazing",
    "reading",
    "listening",
    "phone",
    "organizing",
    "resting",
    "washing",
    "eating",
    "preparing_sleep",
    "gaming",
}


def choose_activity(
    *,
    phase,
    energy,
    social_desire,
    sleep_state,
    weather=None,
    current_activity=None,
    recent_history=None,
):
    # 睡眠状态永远优先于普通生活模拟
    if sleep_state == "sleeping":
        return "sleeping"

    if sleep_state in {
        "sleepy",
        "in_bed",
        "trying_to_sleep",
        "restless",
    }:
        return "preparing_sleep"

    # sleep_engine 明确认为很困时优先休息
    if phase == "sleepy":
        return "resting"

    # 其余时间按照东京现实时间生活
    tokyo_now = datetime.now(
        ZoneInfo("Asia/Tokyo")
    )

    pool = tokyo_daily_pool(
        hour=tokyo_now.hour,
        weekday=tokyo_now.weekday(),
        energy=energy,
        social_desire=social_desire,
    )

    # 东京真实天气只调整室内活动倾向
    pool = apply_tokyo_weather_to_pool(
        pool,
        weather,
    )

    pool = apply_tokyo_schedule_rules(
        pool,
        hour=tokyo_now.hour,
        current_activity=current_activity,
        recent_history=recent_history or [],
    )

    return random.choice(pool)


def should_change_activity(
    *,
    activity,
    elapsed_minutes,
    phase,
    energy,
):
    if activity == "sleeping":
        return False

    if activity == "preparing_sleep":
        return elapsed_minutes >= 20

    if activity == "eating":
        return elapsed_minutes >= 30

    if activity == "washing":
        return elapsed_minutes >= 20

    if activity == "resting":
        minimum = 25 if energy < 0.35 else 15
        return elapsed_minutes >= minimum

    if activity == "gaming":
        if elapsed_minutes < 35:
            return False

        chance = 0.18

        if elapsed_minutes >= 60:
            chance += 0.25

        if elapsed_minutes >= 90:
            chance += 0.30

        if elapsed_minutes >= 120:
            chance += 0.20

        return random.random() < min(chance, 0.90)

    if activity in {
        "reading",
        "listening",
        "phone",
        "organizing",
        "dazing",
        "idle",
    }:
        minimum = 25

        if phase == "evening":
            minimum = 35

        if elapsed_minutes < minimum:
            return False

        chance = 0.20

        if elapsed_minutes >= 60:
            chance += 0.30

        if elapsed_minutes >= 90:
            chance += 0.30

        return random.random() < min(chance, 0.90)

    return elapsed_minutes >= 30


from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.activity.life_state import (
    get_life_state,
    update_life_state,
    record_activity_history,
    get_recent_activity_history,
)
from app.activity.home_world import (
    get_home_world,
    update_home_world,
    room_location_for_activity,
)
from app.tools.weather_cache import get_cached_weather


GAMES = (
    "Minecraft",
    "崩坏：星穹铁道",
    "Muse Dash",
)


async def sync_home_world(activity):
    world = await get_home_world()

    location = room_location_for_activity(activity)
    tokyo_hour = world["tokyo_hour"]

    # 房间灯光按东京现实时间自然变化
    if activity == "sleeping":
        light_state = "off"
    elif tokyo_hour >= 18 or tokyo_hour < 6:
        light_state = "on"
    else:
        light_state = "off"

    if activity == "gaming":
        if world["current_game"]:
            game = world["current_game"]
            started_at = world["game_started_at"]
        else:
            game = random.choice(GAMES)
            started_at = datetime.now(timezone.utc).isoformat()

        await update_home_world(
            room_location=location,
            light_state=light_state,
            current_game=game,
            game_started_at=started_at,
        )
    else:
        await update_home_world(
            room_location=location,
            light_state=light_state,
            clear_game=True,
        )


def activity_elapsed_minutes(started_at):
    if not started_at:
        return None

    started = datetime.fromisoformat(started_at)

    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    now_dt = datetime.now(timezone.utc)

    return max(
        0.0,
        (now_dt - started).total_seconds() / 60,
    )


async def activity_tick(phase):
    life = await get_life_state()

    elapsed = activity_elapsed_minutes(
        life["activity_started_at"]
    )

    must_choose = (
        life["activity_started_at"] is None
        or life["activity"] == "idle"
    )

    if not must_choose:
        must_choose = should_change_activity(
            activity=life["activity"],
            elapsed_minutes=elapsed or 0,
            phase=phase,
            energy=life["energy"],
        )

    if not must_choose:
        await sync_home_world(life["activity"])

        return {
            "action": "no_change",
            "activity": life["activity"],
        }

    # 东京固定天气由 VPS 每2小时刷新。
    # 这里仅读取本地缓存，不额外请求天气 API。
    tokyo_weather = None

    try:
        cached = await get_cached_weather(
            "35.676,139.65"
        )

        if cached:
            tokyo_weather = cached.get("weather")

    except Exception:
        # 天气读取失败不能影响 Life State。
        tokyo_weather = None

    try:
        recent_history = await get_recent_activity_history(limit=8)
    except Exception:
        recent_history = []

    new_activity = choose_activity(
        phase=phase,
        energy=life["energy"],
        social_desire=life["social_desire"],
        sleep_state=life["sleep_state"],
        weather=tokyo_weather,
        current_activity=life["activity"],
        recent_history=recent_history,
    )

    if new_activity == life["activity"]:
        return {
            "action": "no_change",
            "activity": life["activity"],
        }

    # 活动真正发生变化前，保存上一段真实生活轨迹
    previous_game = None

    if life["activity"] == "gaming":
        try:
            world_before_change = await get_home_world()
            previous_game = world_before_change.get("current_game")
        except Exception:
            previous_game = None

    await record_activity_history(
        life["activity"],
        started_at=life["activity_started_at"],
        ended_at=datetime.now(timezone.utc).isoformat(),
        game_name=previous_game,
    )

    updated = await update_life_state(
        activity=new_activity
    )

    await sync_home_world(updated["activity"])

    return {
        "action": "changed",
        "activity": updated["activity"],
        "started_at": updated["activity_started_at"],
    }


def tokyo_daily_pool(hour, weekday, energy, social_desire):
    """
    萤的东京居家日常节奏。
    weekday: 0=周一 ... 6=周日
    """
    weekend = weekday >= 5

    # 早晨
    if 6 <= hour < 9:
        pool = [
            "washing",
            "phone",
            "eating",
            "organizing",
            "listening",
        ]

    # 上午
    elif 9 <= hour < 12:
        pool = [
            "reading",
            "organizing",
            "listening",
            "phone",
            "gaming",
        ]

    # 中午
    elif 12 <= hour < 14:
        pool = [
            "eating",
            "resting",
            "phone",
            "dazing",
        ]

    # 下午
    elif 14 <= hour < 18:
        pool = [
            "gaming",
            "gaming",
            "reading",
            "listening",
            "phone",
            "dazing",
            "organizing",
        ]

    # 晚上
    elif 18 <= hour < 22:
        pool = [
            "gaming",
            "gaming",
            "phone",
            "listening",
            "eating",
            "reading",
            "resting",
        ]

    # 深夜
    elif 22 <= hour or hour < 2:
        pool = [
            "phone",
            "resting",
            "listening",
            "washing",
            "preparing_sleep",
            "dazing",
        ]

    # 凌晨
    else:
        pool = [
            "resting",
            "preparing_sleep",
            "phone",
            "dazing",
        ]

    # 周末更容易宅着打游戏/赖着
    if weekend:
        pool += [
            "gaming",
            "gaming",
            "phone",
            "resting",
        ]

    # 精力低
    if energy < 0.35:
        pool += [
            "resting",
            "resting",
            "dazing",
        ]

    # 很想聊天时更容易拿手机
    if social_desire > 0.65:
        pool += [
            "phone",
            "phone",
        ]

    return pool


def apply_tokyo_weather_to_pool(pool, weather):
    """
    根据东京真实天气调整室内活动倾向。
    不生成外出行为，只改变房间内活动权重。
    """
    if not weather:
        return pool

    condition = str(weather.get("weather") or "")
    temp = weather.get("temperature")
    rain = weather.get("today_rain_probability")

    adjusted = list(pool)

    # 下雨/阴天：更宅、更安静
    if (
        "雨" in condition
        or "雪" in condition
        or "阴" in condition
        or (rain is not None and rain >= 60)
    ):
        adjusted += [
            "gaming",
            "gaming",
            "listening",
            "phone",
            "resting",
            "reading",
        ]

    # 晴天：更容易坐窗边、整理、看东西
    if "晴" in condition:
        adjusted += [
            "dazing",
            "reading",
            "organizing",
            "listening",
        ]

    # 很热：少折腾，多休息/玩手机
    if temp is not None and temp >= 30:
        adjusted += [
            "resting",
            "phone",
            "listening",
        ]

    # 偏冷：更容易窝床/休息
    if temp is not None and temp <= 10:
        adjusted += [
            "resting",
            "phone",
            "reading",
        ]

    return adjusted



def _recently_did(recent_history, activity, within_minutes):
    now_utc = datetime.now(timezone.utc)

    for item in recent_history:
        if item.get("activity") != activity:
            continue

        stamp = item.get("ended_at") or item.get("created_at")

        if not stamp:
            continue

        try:
            dt = datetime.fromisoformat(stamp)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            minutes = (
                now_utc - dt.astimezone(timezone.utc)
            ).total_seconds() / 60

            if 0 <= minutes <= within_minutes:
                return True

        except Exception:
            continue

    return False


def apply_tokyo_schedule_rules(
    pool,
    *,
    hour,
    current_activity=None,
    recent_history=None,
):
    """
    东京居家日程层：
    - 三餐有明显时间节点
    - 洗漱集中在早晚
    - 避免短时间重复
    """
    recent_history = recent_history or []
    adjusted = list(pool)

    # 早餐 7-9
    if 7 <= hour < 9:
        if not _recently_did(
            recent_history,
            "eating",
            150,
        ):
            adjusted += [
                "eating",
                "eating",
                "eating",
            ]

    # 午饭 12-14
    elif 12 <= hour < 14:
        if not _recently_did(
            recent_history,
            "eating",
            180,
        ):
            adjusted += [
                "eating",
                "eating",
                "eating",
                "eating",
            ]

    # 晚饭 18-20
    elif 18 <= hour < 20:
        if not _recently_did(
            recent_history,
            "eating",
            210,
        ):
            adjusted += [
                "eating",
                "eating",
                "eating",
                "eating",
            ]

    # 已经刚吃过，就暂时不要继续抽到吃饭
    if _recently_did(
        recent_history,
        "eating",
        120,
    ):
        adjusted = [
            x for x in adjusted
            if x != "eating"
        ]

    # 早晨洗漱
    if 6 <= hour < 9:
        if not _recently_did(
            recent_history,
            "washing",
            180,
        ):
            adjusted += [
                "washing",
                "washing",
            ]

    # 晚间洗漱 / 洗澡
    if 21 <= hour < 24:
        if not _recently_did(
            recent_history,
            "washing",
            240,
        ):
            adjusted += [
                "washing",
                "washing",
                "washing",
            ]

    # 深夜逐渐进入睡前状态
    if hour >= 23 or hour < 2:
        adjusted += [
            "preparing_sleep",
            "preparing_sleep",
            "resting",
        ]

    # 避免刚结束某活动又马上回去
    if recent_history:
        last_activity = recent_history[0].get(
            "activity"
        )

        if last_activity:
            filtered = [
                x for x in adjusted
                if x != last_activity
            ]

            # 防止过滤成空池
            if filtered:
                adjusted = filtered

    # 当前活动也稍微避开
    if current_activity:
        filtered = [
            x for x in adjusted
            if x != current_activity
        ]

        if filtered:
            adjusted = filtered

    return adjusted
