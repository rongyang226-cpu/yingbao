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
    "walking",
    "coffee",
    "shopping",
}


async def choose_activity(
    *,
    phase,
    energy,
    social_desire,
    sleep_state,
    weather=None,
    current_activity=None,
    recent_history=None,
    needs=None,
    household=None,
    shopping_list=None,
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

    adjusted_pool = list(pool)

    if needs:
        for activity in set(pool):
            bonus = activity_need_bonus(
                activity,
                needs,
            )
            copies = int(round(bonus * 3))
            if copies > 0:
                adjusted_pool.extend(
                    [activity] * copies
                )

    for activity in {"organizing", "shopping"}:
        bonus = activity_domestic_bonus(
            activity,
            household or {},
            shopping_list or [],
        )
        copies = int(round(bonus * 3))
        if copies > 0:
            adjusted_pool.extend(
                [activity] * copies
            )

    pool = adjusted_pool

    return await weighted_choice(
        "activity",
        pool,
    )


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
        "walking",
        "coffee",
        "shopping",
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
from app.activity.entertainment import play_entertainment
from app.activity.life_log import write_life_log
from app.activity.home_world import (
    get_home_world,
    update_home_world,
    room_location_for_activity,
)
from app.tools.weather_cache import get_cached_weather
from app.activity.diary import write_diary
from app.activity.world_state import sync_presence_for_activity
from app.activity.plan_engine import ensure_today_plan, get_current_intention, complete_matching_intention, expire_old_slots, reconsider_today_plan
from app.activity.attention import attention_blocks_activity_change
from app.activity.continuity import (
    get_continuity_state,
    start_activity_intention,
    mark_interrupted,
    resolve_interruption,
    finish_activity_intention,
)
from app.activity.impulses import (
    get_actionable_impulse,
    mark_impulse_started,
    complete_active_impulse,
    defer_impulse,
)
from app.activity.needs import (
    get_needs,
    activity_need_bonus,
    satisfy_need_for_completed_activity,
)
from app.activity.inventory import (
    get_inventory,
    consume_for_activity,
)
from app.activity.domestic import (
    get_pantry,
    choose_and_consume_meal,
    perform_shopping,
    perform_household_chore,
    update_outfit,
    get_household_state,
    get_shopping_list,
    activity_domestic_bonus,
)
from app.activity.interests import weighted_choice, record_interest_event, relax_boredom


GAMES = (
    "Minecraft",
    "崩坏：星穹铁道",
    "Muse Dash",
)


async def sync_home_world(activity, *, allow_world_move=False):
    world = await get_home_world()

    location = room_location_for_activity(activity)
    tokyo_hour = world["tokyo_hour"]

    # 小世界地点：只有活动真正变化时才允许随机换地点；
    # 睡眠/洗漱/游戏等强地点活动会自动同步。
    presence_result = None
    try:
        cached_weather = await get_cached_weather(
            "35.676,139.65"
        )
        weather_for_world = (
            cached_weather.get("weather")
            if cached_weather
            else None
        )
        presence_result = await sync_presence_for_activity(
            activity,
            weather=weather_for_world,
            allow_move=allow_world_move,
        )
        if presence_result and presence_result.get("place_key"):
            location = presence_result["place_key"]
    except Exception:
        # 世界地点同步失败不能影响主生活循环。
        pass

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
            # 此时只是进入游戏时间，
            # 真正的游戏名称要等真实引擎运行后才能确定。
            game = "准备选择游戏"
            started_at = datetime.now(timezone.utc).isoformat()

        await update_home_world(
            room_location=location,
            light_state=light_state,
            current_game=game,
            game_started_at=started_at,
        )
    else:
        if (
            activity == "phone"
            and world.get("current_entertainment_mode") == "media"
        ):
            # 刷视频属于 phone 活动，但仍是正在进行的娱乐；
            # 普通同步不能把它当作旧游戏状态清掉。
            await update_home_world(
                room_location=location,
                light_state=light_state,
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


def _parse_entertainment_detail(detail):
    result = {
        "mood": "",
        "reaction": "",
        "session": "",
    }

    if not detail:
        return result

    text = str(detail)

    for key in result:
        tag = key + "="
        pos = text.find(tag)

        if pos < 0:
            continue

        start = pos + len(tag)
        ends = []

        for other in result:
            if other == key:
                continue

            p = text.find(
                "; " + other + "=",
                start,
            )

            if p >= 0:
                ends.append(p)

        end = min(ends) if ends else len(text)

        result[key] = text[start:end].strip()

    return result


def _mood_cn(mood):
    names = {
        "excited": "很兴奋",
        "proud": "得意",
        "happy": "开心",
        "mixed": "有点复杂",
        "annoyed": "有点不爽",
        "frustrated": "很烦",
        "confused": "有点懵",
    }

    return names.get(
        str(mood or ""),
        str(mood or ""),
    )


def _activity_log_content(activity):
    choices = {
        "idle": (
            "有点无聊",
            "无聊",
            [
                "不知道干嘛，先待一会儿。",
                "突然没什么想做的……",
                "有点闲下来了。",
            ],
        ),
        "dazing": (
            "在发呆",
            "放空",
            [
                "脑子暂时不想转了。",
                "就这样发会儿呆也挺好。",
                "什么都不想干一会儿。",
            ],
        ),
        "resting": (
            "在休息",
            "放松",
            [
                "先歇一会儿。",
                "稍微躺平一下。",
                "休息一下再说。",
            ],
        ),
        "reading": (
            "在看东西",
            "平静",
            [
                "随便看看。",
                "安静看一会儿东西。",
            ],
        ),
        "listening": (
            "在听东西",
            "放松",
            [
                "听点东西混时间。",
                "安静听一会儿。",
            ],
        ),
        "phone": (
            "在玩手机",
            "随意",
            [
                "随便划两下。",
                "没什么目的地刷一会儿。",
            ],
        ),
        "walking": (
            "出去走走",
            "放松",
            [
                "天气还行，出去晃一会儿。",
                "在附近慢慢走走。",
            ],
        ),
        "coffee": (
            "去附近坐一会儿",
            "放松",
            [
                "找个地方坐会儿，换换脑子。",
                "想安静坐一阵。",
            ],
        ),
        "shopping": (
            "去附近买点东西",
            "随意",
            [
                "顺路补点日用品。",
                "出去买点东西，很快就回来。",
            ],
        ),
    }

    item = choices.get(activity)

    if not item:
        return None

    detail, mood, thoughts = item

    return {
        "detail": detail,
        "mood": mood,
        "thought": random.choice(thoughts),
    }



async def activity_tick(phase):
    life = await get_life_state()

    # 正在真实聊天时，短时间内不随机把生活活动切走。
    # 睡眠引擎仍然独立优先处理，不受这里影响。
    try:
        if (
            life.get("sleep_state") == "awake"
            and await attention_blocks_activity_change()
        ):
            await mark_interrupted(
                life["activity"],
                reason="conversation",
            )
            await sync_home_world(life["activity"])
            return {
                "action": "attention_hold",
                "activity": life["activity"],
            }
    except Exception:
        pass

    # 聊天已经安静下来：只在这里做一次“继续/放弃”的连续性决策。
    force_choose = False
    try:
        continuity_result = await resolve_interruption(
            life["activity"]
        )
        if continuity_result.get("action") == "resume":
            life = await update_life_state(
                activity_started_at=datetime.now(
                    timezone.utc
                ).isoformat()
            )
            await sync_home_world(life["activity"])
            return {
                "action": "resumed_after_conversation",
                "activity": life["activity"],
            }
        elif continuity_result.get("action") == "abandon":
            force_choose = True
        elif life.get("activity") not in {
            "sleeping",
            "preparing_sleep",
        }:
            continuity_state = await get_continuity_state()
            if (
                continuity_state.get("status") in {
                    "idle", "completed", "abandoned"
                }
                or continuity_state.get("intended_activity")
                != life["activity"]
            ):
                await start_activity_intention(
                    life["activity"],
                    source="existing_state",
                    reason="continuity_bootstrap",
                )
    except Exception:
        force_choose = False

    elapsed = activity_elapsed_minutes(
        life["activity_started_at"]
    )

    must_choose = (
        force_choose
        or life["activity_started_at"] is None
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

    # 今天的生活计划不是硬脚本：只是给当前时段一个明显倾向。
    # 天气变化、睡眠状态、精力仍然可以让她改变主意。
    try:
        await expire_old_slots()
        await ensure_today_plan(
            weather=tokyo_weather
        )
        await reconsider_today_plan(
            weather=tokyo_weather
        )
        current_intention = await get_current_intention()
    except Exception:
        current_intention = None

    try:
        current_needs = await get_needs()
    except Exception:
        current_needs = {}

    try:
        household_state = await get_household_state()
        shopping_list = await get_shopping_list()
    except Exception:
        household_state = {}
        shopping_list = []

    new_activity = await choose_activity(
        phase=phase,
        energy=life["energy"],
        social_desire=life["social_desire"],
        sleep_state=life["sleep_state"],
        weather=tokyo_weather,
        current_activity=life["activity"],
        recent_history=recent_history,
        needs=current_needs,
        household=household_state,
        shopping_list=shopping_list,
    )

    try:
        actionable_impulse = await get_actionable_impulse()
    except Exception:
        actionable_impulse = None

    # 当前时段计划会提高被选中的概率，但不会强制执行。
    if (
        current_intention
        and current_intention.get("status") == "planned"
        and current_intention.get("activity") != life["activity"]
        and life.get("sleep_state") == "awake"
        and phase != "sleepy"
    ):
        if random.random() < 0.62:
            new_activity = current_intention["activity"]

    # 临时念头只是一个软倾向，不是任务命令。
    if (
        actionable_impulse
        and life.get("sleep_state") == "awake"
        and phase != "sleepy"
    ):
        strength = float(actionable_impulse.get("strength") or 0.5)
        impulse_chance = min(0.72, 0.22 + strength * 0.55)

        # 当前已有明确日计划时，临时念头更不容易把计划顶掉。
        if (
            current_intention
            and current_intention.get("status") == "planned"
            and new_activity == current_intention.get("activity")
        ):
            impulse_chance *= 0.62

        if random.random() < impulse_chance:
            new_activity = actionable_impulse["activity"]
        elif random.random() < 0.18:
            try:
                await defer_impulse(
                    actionable_impulse["id"],
                    reason="not_now",
                )
            except Exception:
                pass

    # 需要实际物资的活动先检查库存；缺货时不允许“假装完成”。
    if new_activity in {"eating", "washing"}:
        try:
            if new_activity == "eating":
                pantry = await get_pantry()
                edible = sum(
                    float(x["quantity"])
                    for x in pantry
                    if x["category"] in {"meal", "snack"}
                )
                if edible < 1.0:
                    new_activity = "shopping"
            elif new_activity == "washing":
                inv = await get_inventory()
                if inv["bath_supplies"]["quantity"] < 1.0:
                    new_activity = "shopping"
        except Exception:
            pass

    if new_activity == life["activity"]:
        if (
            actionable_impulse
            and actionable_impulse.get("activity") == life["activity"]
        ):
            try:
                await mark_impulse_started(life["activity"])
            except Exception:
                pass
        return {
            "action": "no_change",
            "activity": life["activity"],
        }

    # 活动真正发生变化前，先结算上一段生活轨迹。
    previous_game = None
    history_mode = "normal"
    history_detail = None

    if life["activity"] == "gaming":
        try:
            world_before_change = await get_home_world()

            previous_game = world_before_change.get(
                "current_game"
            )

            history_mode = (
                world_before_change.get(
                    "current_entertainment_mode"
                )
                or "simulated"
            )

            history_detail = (
                world_before_change.get(
                    "current_entertainment_detail"
                )
            )

        except Exception as exc:
            history_mode = "failed"
            history_detail = (
                "entertainment_state_read_failed="
                + str(exc)
            )

    await record_activity_history(
        life["activity"],
        started_at=life["activity_started_at"],
        ended_at=datetime.now(timezone.utc).isoformat(),
        game_name=previous_game,
        mode=history_mode,
        detail=history_detail,
        duration_minutes=elapsed,
    )

    # 真正做完一段活动后，才让“萤自己的兴趣”产生极小变化。
    # 必需生活行为（吃饭、洗漱、睡眠等）不参与兴趣成长。
    old_activity_for_interest = life.get("activity")
    if (
        old_activity_for_interest in {
            "reading", "listening", "walking", "coffee",
            "organizing", "shopping", "gaming", "resting",
        }
        and (elapsed or 0) >= 15
    ):
        try:
            await record_interest_event(
                kind="activity",
                name=old_activity_for_interest,
                event="completed",
            )
            await relax_boredom()
        except Exception:
            pass

    if life["activity"] == "gaming":
        parsed = _parse_entertainment_detail(
            history_detail
        )

        duration_text = ""

        if elapsed is not None:
            duration_text = (
                f"，玩了约{max(1, round(elapsed))}分钟"
            )

        write_life_log(
            activity="gaming",
            event="finished",
            mode=history_mode,
            detail=(
                f"结束玩{previous_game or '游戏'}"
                + duration_text
            ),
            mood=_mood_cn(
                parsed.get("mood")
            ),
            thought=parsed.get(
                "reaction"
            ),
            source="activity_engine",
        )


        # 私人日记：主观记录，和客观 life_log 分开。
        diary_mood = _mood_cn(
            parsed.get("mood")
        )

        diary_reaction = (
            parsed.get("reaction")
            or ""
        ).strip()

        diary_game = (
            previous_game
            or "游戏"
        )

        diary_content = (
            f"刚结束《{diary_game}》"
            + duration_text
            + "。"
        )

        if diary_reaction:
            diary_content += (
                "\n\n"
                + diary_reaction
            )

        write_diary(
            content=diary_content,
            mood=diary_mood or None,
            title="游戏后的碎碎念",
        )

    # 普通生活活动结束后的私人碎碎念。
    # gaming 已由上面的真实游戏结果单独处理。
    if life["activity"] != "gaming":
        old_activity = life.get("activity") or "idle"

        diary_activity_names = {
            "idle": "闲着",
            "dazing": "发呆",
            "reading": "看东西",
            "listening": "听东西",
            "phone": "看手机",
            "organizing": "整理东西",
            "resting": "休息",
            "washing": "洗漱",
            "eating": "吃东西",
            "preparing_sleep": "准备睡觉",
            "sleeping": "睡觉",
            "walking": "出去散步",
            "coffee": "在附近坐着休息",
            "shopping": "出去买东西",
        }

        diary_thoughts = {
            "idle": "就这么安静待了一会儿。",
            "dazing": "脑子放空了一会儿，也挺舒服的。",
            "reading": "先看到这里，之后有兴趣再继续。",
            "listening": "安安静静听了一阵。",
            "phone": "又抱着手机消磨了一会儿时间。",
            "organizing": "收拾完以后看着顺眼多了。",
            "resting": "稍微休息了一阵，精神缓过来一点。",
            "washing": "洗漱完了，整个人清爽不少。",
            "eating": "吃完了，先歇一会儿。",
            "preparing_sleep": "该慢慢安静下来了。",
            "sleeping": "这一觉算是睡完了。",
            "walking": "出去走了一圈，脑子清醒了一点。",
            "coffee": "换了个地方坐会儿，感觉还不错。",
            "shopping": "该买的东西差不多补齐了。",
        }

        activity_name = diary_activity_names.get(
            old_activity,
            "做自己的事",
        )

        duration_text = ""

        if elapsed is not None:
            duration_text = (
                f"，大概{max(1, round(elapsed))}分钟"
            )

        content = (
            f"刚结束{activity_name}{duration_text}。"
        )

        thought = diary_thoughts.get(old_activity)

        if thought:
            content += "\n\n" + thought

        write_diary(
            content=content,
            title="生活碎片",
        )

    try:
        await finish_activity_intention(
            life["activity"],
            reason="activity_changed",
        )
    except Exception:
        pass

    try:
        await complete_active_impulse(
            life["activity"],
            reason="activity_finished",
        )
    except Exception:
        pass

    try:
        if life["activity"] == "shopping":
            bought = await perform_shopping()
            bought_text = (
                "、".join(
                    f"{name}{qty:g}{unit}"
                    for name, qty, unit in bought
                )
                if bought
                else "这次没有缺的东西"
            )
            write_life_log(
                activity="shopping",
                event="restocked",
                mode="real",
                detail=f"补货：{bought_text}",
                mood="",
                thought="",
                source="domestic",
            )
        elif life["activity"] == "organizing":
            chore = await perform_household_chore()
            write_life_log(
                activity="organizing",
                event="chore_done",
                mode="real",
                detail=chore.get("description") or "做了家务",
                mood="",
                thought="",
                source="domestic",
            )

        await satisfy_need_for_completed_activity(
            life["activity"]
        )
    except Exception:
        pass

    updated = await update_life_state(
        activity=new_activity
    )

    # 真正进入吃饭/洗漱时才扣真实库存。
    # 如果极端并发下库存刚好耗尽，则退回 shopping，绝不伪造已消费。
    if updated["activity"] == "eating":
        try:
            meal_result = await choose_and_consume_meal(
                hunger=current_needs.get("hunger")
            )
            if not meal_result.get("ok"):
                updated = await update_life_state(
                    activity="shopping"
                )
                new_activity = "shopping"
            else:
                write_life_log(
                    activity="eating",
                    event="meal_selected",
                    mode="real",
                    detail=(
                        f"{meal_result.get('preparation') or '准备了吃的'}；"
                        f"这次吃{meal_result['item_name']}"
                    ),
                    mood="",
                    thought="",
                    source="domestic",
                )
        except Exception:
            pass
    elif updated["activity"] == "washing":
        try:
            consume_result = await consume_for_activity("washing")
            if not consume_result.get("ok"):
                updated = await update_life_state(
                    activity="shopping"
                )
                new_activity = "shopping"
        except Exception:
            pass

    try:
        await update_outfit(
            activity=updated["activity"],
            weather=tokyo_weather,
            sleep_state=updated.get("sleep_state", "awake"),
        )
    except Exception:
        pass

    try:
        await start_activity_intention(
            updated["activity"],
            source=(
                "spontaneous_impulse"
                if actionable_impulse
                and actionable_impulse.get("activity") == updated["activity"]
                else (
                    "daily_plan"
                    if current_intention
                    and current_intention.get("activity")
                    == updated["activity"]
                    else "autonomous"
                )
            ),
            reason="activity_selected",
        )
    except Exception:
        pass

    try:
        await mark_impulse_started(
            updated["activity"]
        )
    except Exception:
        pass

    try:
        await complete_matching_intention(
            updated["activity"]
        )
    except Exception:
        pass

    # 真正进入 gaming 的这一刻才启动娱乐。
    if updated["activity"] == "gaming":
        # 进入游戏活动时，真实位置同步到游戏房。
        await sync_home_world(
            "gaming",
            allow_world_move=True,
        )

        try:
            game_result = await play_entertainment()

            ent_mode = game_result.get(
                "mode",
                "simulated",
            )

            ent_game = game_result.get(
                "game"
            ) or "未知娱乐"

            ent_detail = (
                f'mood={game_result.get("mood")}; '
                f'reaction={game_result.get("reaction")}; '
                f'session={game_result.get("session_file")}'
            )

            if ent_mode == "media":
                # 媒体摸鱼不是“玩游戏”。把生活层也同步为看手机，
                # 并让当前位置与 Home World 使用同一个真实地点。
                previous_started_at = updated.get("activity_started_at")
                updated = await update_life_state(
                    activity="phone",
                    activity_started_at=previous_started_at,
                )
                try:
                    await finish_activity_intention(
                        "gaming",
                        reason="media_mode_selected",
                    )
                    await start_activity_intention(
                        "phone",
                        source="entertainment_media",
                        reason="media_mode_selected",
                    )
                except Exception:
                    pass

                presence_result = await sync_presence_for_activity(
                    "phone",
                    allow_move=True,
                )
                media_location = (
                    (presence_result or {}).get("place_key")
                    or room_location_for_activity("phone")
                )

                await update_home_world(
                    room_location=media_location,
                    current_game=ent_game,
                    game_started_at=datetime.now(
                        timezone.utc
                    ).isoformat(),
                    current_entertainment_mode=ent_mode,
                    current_entertainment_detail=ent_detail,
                    current_entertainment_session=None,
                )

                write_life_log(
                    activity="phone",
                    event="started",
                    mode="media",
                    detail=f"开始{ent_game}",
                    mood="",
                    thought="",
                    source="activity_engine",
                )
            else:
                await update_home_world(
                    room_location=room_location_for_activity(
                        "gaming"
                    ),
                    current_game=ent_game,
                    game_started_at=datetime.now(
                        timezone.utc
                    ).isoformat(),
                    current_entertainment_mode=ent_mode,
                    current_entertainment_detail=ent_detail,
                    current_entertainment_session=(
                        game_result.get("session_file")
                    ),
                )

                write_life_log(
                    activity="gaming",
                    event="started",
                    mode=ent_mode,
                    detail=f"开始玩{ent_game}",
                    mood="",
                    thought="",
                    source="activity_engine",
                )

        except Exception as exc:
            # 游戏失败同样写日志，保留发生的时间与技术错误。
            write_life_log(activity="gaming", event="failed", mode="failed", detail="游戏启动失败，未产生真实对局", mood="", thought="详细异常已经写入错误日志。", source="activity_engine")
            from app.live2d.mobile_event_log import record_event
            record_event("游戏错误", "萤的自动游戏启动失败", error=exc)
            await update_home_world(
                room_location=room_location_for_activity(
                    "gaming"
                ),
                current_game="游戏启动失败",
                game_started_at=datetime.now(
                    timezone.utc
                ).isoformat(),
                current_entertainment_mode="failed",
                current_entertainment_detail=(
                    "entertainment_start_failed="
                    + str(exc)
                ),
                current_entertainment_session=None,
            )

    else:
        await sync_home_world(
            updated["activity"],
            allow_world_move=True,
        )

        log_content = _activity_log_content(
            updated["activity"]
        )

        if log_content:
            write_life_log(
                activity=updated["activity"],
                event="started",
                mode="normal",
                detail=log_content["detail"],
                mood=log_content["mood"],
                thought=log_content["thought"],
                source="activity_engine",
            )

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
            "walking",
            "coffee",
        ]

    # 上午
    elif 9 <= hour < 12:
        pool = [
            "reading",
            "organizing",
            "listening",
            "phone",
            "gaming",
            "walking",
            "coffee",
        ]

    # 中午
    elif 12 <= hour < 14:
        pool = [
            "eating",
            "resting",
            "phone",
            "dazing",
            "coffee",
            "shopping",
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
            "walking",
            "coffee",
            "shopping",
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
            "walking",
            "shopping",
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

    # 下雨/雪/高降雨概率：减少外出。
    if (
        "雨" in condition
        or "雪" in condition
        or (rain is not None and rain >= 60)
    ):
        adjusted = [
            x for x in adjusted
            if x not in {"walking", "coffee", "shopping"}
        ]
        adjusted += [
            "gaming",
            "gaming",
            "listening",
            "phone",
            "resting",
            "reading",
        ]
    elif "阴" in condition:
        adjusted += [
            "listening",
            "phone",
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
