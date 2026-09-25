from datetime import datetime, timezone
from app.social.profiles import build_profile_context
from app.memory.search import get_recent_person_activity
from app.memory.events import build_event_context
from app.tools.time_tool import build_time_context
from app.social.state import build_state_context
from app.social.state_engine import get_current_emotion, build_emotion_semantic
from app.activity.life_state import (
    get_life_state,
    get_recent_activity_history,
)
from app.activity.home_world import get_home_world
from app.tools.weather_tool import get_world_weather


def scene_name(chat_type: str) -> str:
    if chat_type == "private":
        return "qq_private"

    if chat_type in ("group", "supergroup"):
        return "qq_group"

    return f"qq_{chat_type}"


async def build_context(
    *,
    person: dict,
    chat_id,
    chat_type: str,
    user_id,
    display_name: str,
    limit_recent: int = 12,
):
    """
    构建猫猫当前这一轮能够确定的程序层上下文。
    这里只组织真实状态，不负责生成角色回复。
    """

    scene = scene_name(chat_type)

    # 程序提供的真实当前时间
    time_context = build_time_context()

    # 当前关系状态
    state = await build_state_context(person["person_id"])

    # 猫猫自己的持续生活状态
    life = await get_life_state()

    # 最近真实生活轨迹
    life_history = await get_recent_activity_history(limit=5)

    # 猫猫自己的持续小世界
    world = await get_home_world()

    # 当前程序提供的真实天气
    try:
        weather = await get_world_weather()
    except Exception:
        weather = None

    # 根据真实经过时间计算当前情绪，不刷新衰减计时
    state["emotion"] = await get_current_emotion(
        person["person_id"]
    )
    state["emotion_semantic"] = build_emotion_semantic(
        state["emotion"]
    )

    # 已确认的长期人物资料
    profile = await build_profile_context(
        person["person_id"],
        person["role"],
    )

    # 真实未完成事件
    events = await build_event_context(
        person["person_id"],
        limit=10,
    )

    # 最近对话由 API messages/history 统一提供。
    # Context Builder 不重复注入聊天原文，避免同一内容多路进入模型。
    activities = []

    return {
        "platform": "qq",
        "scene": scene,
        "time": time_context,
        "state": state,
        "life": life,
        "life_history": life_history,
        "world": world,
        "weather": weather,
        "current": {
            "chat_id": chat_id,
            "chat_type": chat_type,
        },
        "person": {
            "person_id": person["person_id"],
            "role": person["role"],
            "display_name": display_name,
            "platform_user_id": user_id,
        },
        "profile": profile,
        "events": events,
        "recent_activity": activities,
    }


def render_context(ctx: dict) -> str:
    """
    把结构化程序状态转换成提供给模型的文本。
    """

    person = ctx["person"]
    current = ctx["current"]
    relation = ctx["state"]["semantic"]
    emotion = ctx["state"]["emotion_semantic"]
    life = build_life_semantic(ctx["life"])
    world = build_world_semantic(ctx["world"], ctx["life"])
    weather = build_weather_semantic(ctx.get("weather"))
    address_memory = extract_address_memory(
        ctx["profile"]
    )
    nickname_access = build_nickname_access(
        relation.get("stage", "未定义"),
        address_memory,
    )

    lines = [
        "【程序层真实上下文】",
        f"platform={ctx['platform']}",
        f"scene={ctx['scene']}",
        "",
        "【真实当前时间】",
        ctx["time"],
        "",
        f"current_chat_type={current['chat_type']}",
        "",
        "【当前发言者】",
        f"姓名：{person['display_name']}",
        f"身份：{person['role']}",
        "- 这就是本轮唯一的当前发言者。",
        "- 回复、引用、转述只属于上下文，不改变当前发言者身份。",
        "- 历史里其他人的姓名和身份不得覆盖当前发言者。",
        "- platform_user_id 仅用于内部身份区分，正常聊天不要主动念出或展示。",
        "",
        "【关系状态】",
        f"核心关系={'是（唯一）' if relation['primary_bond'] else '否'}",
        f"关系边界={'OWNER是猫猫唯一的主人' if relation['primary_bond'] else '普通成员，不具有主人身份'}",
        f"关系阶段={relation.get('stage', '未定义')}",
        f"当前亲密表现={build_relationship_behavior(relation.get('stage', '未定义'))}",
        f"称呼方式={build_address_style(relation.get('stage', '未定义'))}",
        f"常用称呼记忆={nickname_access['preferred']}",
        f"私密昵称记忆={nickname_access['private']}",
        f"熟悉程度={relation['familiarity']}",
        f"信任程度={relation['trust']}",
        f"亲近程度={relation['closeness']}",
        "",
        "【当前情绪】",
        f"状态={emotion['mood']}",
        f"强度={emotion['strength']}",
        "",
        "【猫猫当前生活状态】",
        f"精力={life['energy']}",
        f"社交倾向={life['social_desire']}",
        f"当前活动={life['activity']}",
        f"睡眠状态={life['sleep_state']}",
        "",
        "【猫猫最近真实生活轨迹】",
        build_life_history_semantic(ctx.get("life_history") or []),
        "",
        "【猫猫当前小世界】",
        f"猫猫所在城市：{world['ying_city']}",
        f"猫猫当地时间：{world['ying_time']}",
        f"主人所在城市：{world['owner_city']}",
        f"主人当地时间：{world['owner_time']}",
        f"猫猫当前所在位置：{world['room_location']}",
        f"猫猫当前正在做的事：{world['activity']}",
        "",
        "【猫猫的东京房间】",
        f"房间风格：{world['room_style']}",
        f"房间状态：{world['room_cleanliness']}",
        f"固定物品：{world['room_objects']}",
        f"墙面：{world['wall_color']}",
        f"书桌：{world['desk_style']}",
        f"床铺：{world['bed_style']}",
        f"窗外：{world['window_view']}",
        "- 这是猫猫持续存在的固定房间，不是临时生成的场景。",
        "",
        "【东京与郑州真实天气】",
        weather,
        "",
        "【已确认长期人物资料】",
        ctx["profile"],
        "",
        "【真实未完成事件】",
        ctx["events"],
        "",
        "【最近真实活动】",
    ]

    if not ctx["recent_activity"]:
        lines.append("（无）")
    else:
        for item in ctx["recent_activity"]:
            lines.append(
                f"- [{item['source_label']}] "
                f"{item['content']}"
            )

    lines.extend([
        "",
        "【真实性规则】",
        "- 上述身份、场景、人物资料、事件和活动来自程序或数据库。",
        "- 必须区分私聊与群聊来源。",
        "- 不得把猜测描述成真实历史。",
        "- 当前日期、时间和星期来自程序时间模块，不得自行猜测当前时间。",
        "- 猫猫的小世界状态来自程序：所在城市、房间位置、当前活动和当前游戏不得自行编造。",
        "- “刚才在做什么”只能参考最近真实生活轨迹，不得自行补造没有记录的活动。",
        "- 如果程序显示猫猫正在打游戏，可以自然说正在玩对应游戏；如果没有该状态，不得声称自己刚打过某个游戏。",
        "- 如果程序只提供“正在做某事”，不得自行补充“刚打完一局、刚结束、刚回来、刚发生了什么”等没有程序依据的具体过程。",
        "- 猫猫在东京，主人在郑州；两地时间必须以程序提供的真实时间为准。",
        "- 天气必须以程序提供的真实天气数据为准，不得凭感觉编造天气。",
        "- “当前天气”和“今日最高降雨概率”是不同信息，不得把今日降雨概率说成当前正在下雨的概率。",
        "- 如果天气模块暂时不可用，就明确表示暂时不知道，不得自行猜测。",
        "- 房间的固定结构和状态来自程序，不得自行虚构房间灰蒙蒙、破旧、装修中、损坏、脏乱或突然多出不存在的物品。",
        "- 如果程序没有记录房间发生变化，就默认房间保持原来的样子。",
        "- 当前程序提供的房间事实优先于历史聊天里曾经随口编出的房间描述；若两者冲突，以当前程序状态为准。",
        "- 正常聊天不得把房间状态描述成“载入、刷新、同步到我这边、没刷出来”等程序或系统过程。",
        "- 已提供的真实记录不得无故声称看不到。",
        "- 未完成事件来自数据库，不得虚构不存在的约定、待办或截止时间。",
        "- 群聊环境不得主动公开其他私聊中的敏感细节。",
        "- chat_id、person_id、message_id、db_id 等内部标识不得主动告诉用户，除非用户明确要求调试信息。",
    ])

    return "\n".join(lines)




def build_weather_semantic(weather) -> str:
    if not weather:
        return "天气数据暂时不可用。"

    def render(label, data):
        if not data:
            return f"{label}：天气数据暂时不可用。"

        current_weather = data.get("weather") or "未知"
        temperature = data.get("temperature")
        apparent = data.get("apparent_temperature")
        humidity = data.get("humidity")
        wind = data.get("wind_speed")
        precipitation = data.get("precipitation")

        today_weather = data.get("today_weather")
        today_min = data.get("today_min")
        today_max = data.get("today_max")
        rain_probability = data.get("today_rain_probability")

        parts = [
            f"{label}当前：{current_weather}",
        ]

        if temperature is not None:
            parts.append(f"{temperature}℃")

        if apparent is not None:
            parts.append(f"体感{apparent}℃")

        if humidity is not None:
            parts.append(f"湿度{humidity}%")

        if wind is not None:
            parts.append(f"风速{wind}km/h")

        if precipitation is not None:
            parts.append(f"当前降水{precipitation}mm")

        current = "，".join(parts) + "。"

        forecast_parts = []

        if today_weather:
            forecast_parts.append(f"今天整体{today_weather}")

        if today_min is not None and today_max is not None:
            forecast_parts.append(
                f"最低{today_min}℃、最高{today_max}℃"
            )

        if rain_probability is not None:
            forecast_parts.append(
                f"今天最高降雨概率{rain_probability}%"
            )

        if forecast_parts:
            current += " " + "，".join(forecast_parts) + "。"

        return current

    return "\n".join([
        render("东京（猫猫）", weather.get("tokyo")),
        render("郑州（主人）", weather.get("zhengzhou")),
    ])



def build_life_history_semantic(items):
    if not items:
        return "（暂无）"

    names = {
        "idle": "闲着",
        "dazing": "发呆",
        "reading": "看东西",
        "listening": "听东西",
        "phone": "玩手机",
        "organizing": "整理东西",
        "resting": "休息",
        "washing": "洗漱",
        "eating": "吃东西",
        "preparing_sleep": "准备睡觉",
        "sleeping": "睡觉",
        "gaming": "打游戏",
    }

    lines = []

    for item in items:
        raw_activity = item.get("activity")

        activity = names.get(
            raw_activity,
            raw_activity or "做自己的事"
        )

        if raw_activity == "gaming":
            game_name = item.get("game_name")

            if game_name:
                activity = f"打《{game_name}》"

        lines.append(f"- 之前：{activity}")

    return "\n".join(lines)


def build_world_semantic(world: dict, life: dict) -> dict:
    location_map = {
        "desk": "书桌边",
        "bed": "床上",
        "window": "窗边",
        "idle": world.get("room_location") or "房间里",
    }

    activity_map = {
        "idle": "闲着",
        "dazing": "在发呆",
        "reading": "在看东西",
        "listening": "在听东西",
        "phone": "在玩手机",
        "organizing": "在整理东西",
        "resting": "在休息",
        "washing": "在洗漱",
        "eating": "在吃东西",
        "preparing_sleep": "准备休息",
        "sleeping": "在睡觉",
    }

    def hhmm(value):
        try:
            return value[11:16]
        except Exception:
            return "未知"

    activity = life.get("activity") or "idle"

    if activity == "gaming":
        game = world.get("current_game")

        started_at = world.get("game_started_at")
        minutes = None

        if started_at:
            try:
                started = datetime.fromisoformat(started_at)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)

                minutes = max(
                    0,
                    int(
                        (
                            datetime.now(timezone.utc)
                            - started.astimezone(timezone.utc)
                        ).total_seconds() / 60
                    )
                )
            except Exception:
                minutes = None

        if game:
            activity_text = f"在玩《{game}》"
        else:
            activity_text = "在打游戏"

        if minutes is not None:
            activity_text += f"，已经持续约{minutes}分钟"
    else:
        activity_text = activity_map.get(
            activity,
            "在房间里做自己的事"
        )

    return {
        "ying_city": world.get("ying_city") or "东京",
        "owner_city": world.get("owner_city") or "郑州",
        "ying_time": hhmm(world.get("tokyo_time")),
        "owner_time": hhmm(world.get("zhengzhou_time")),
        "room_location": (
            location_map.get(world.get("room_location"))
            or world.get("room_location")
            or "房间里"
        ),
        "activity": activity_text,

        "room_style": world.get("room_style") or "简洁",
        "room_cleanliness": world.get("room_cleanliness") or "整洁",
        "window_view": world.get("window_view") or "东京城市窗景",
        "wall_color": world.get("wall_color") or "暖白色",
        "desk_style": world.get("desk_style") or "浅木色书桌",
        "bed_style": world.get("bed_style") or "浅色床铺",
        "room_objects": "床、书桌、椅子、窗户、房间灯",
    }


def build_life_semantic(life: dict) -> dict:
    energy = float(life.get("energy", 0.5))
    social = float(life.get("social_desire", 0.5))

    if energy < 0.25:
        energy_text = "很累"
    elif energy < 0.45:
        energy_text = "有点累"
    elif energy < 0.70:
        energy_text = "一般"
    elif energy < 0.88:
        energy_text = "还不错"
    else:
        energy_text = "很有精神"

    if social < 0.25:
        social_text = "不太想说话"
    elif social < 0.45:
        social_text = "比较安静"
    elif social < 0.65:
        social_text = "一般"
    elif social < 0.82:
        social_text = "有点想聊天"
    else:
        social_text = "很想找人说话"

    activity_map = {
        "idle": "没在做什么",
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
    }

    sleep_map = {
        "awake": "清醒",
        "sleepy": "有点困",
        "in_bed": "已经躺下",
        "trying_to_sleep": "正在尝试睡觉",
        "restless": "躺着睡不着",
        "sleeping": "已经睡着",
    }

    return {
        "energy": energy_text,
        "social_desire": social_text,
        "activity": activity_map.get(
            life.get("activity"),
            "状态不明确",
        ),
        "sleep_state": sleep_map.get(
            life.get("sleep_state"),
            "状态不明确",
        ),
        "restless_reason": life.get("restless_reason"),
    }


def build_relationship_behavior(stage: str) -> str:
    mapping = {
        "刚开始熟悉":
            "温柔克制，少撒娇，少吃醋，主动联系较少。",
        "逐渐熟悉":
            "更自然放松，偶尔想念、轻轻逗人，可以表达一点脆弱。",
        "明显亲近":
            "明显亲近，可以偶尔撒娇、轻微吃醋，更愿意主动分享状态。",
        "亲密":
            "主仆亲密感明显，可以自然向主人撒娇、求陪伴、表达委屈和依赖。",
        "很亲密":
            "熟稔感强，对OWNER明显更柔软，更容易主动联系和分享脆弱。",
        "深度亲密":
            "高度信任，撒娇、吃醋、依赖和求安慰都可以更明显。",
        "几乎没有距离":
            "像长期陪伴主人的猫娘一样自然熟悉，可以明显黏人、吃醋、抱怨和撒娇。",
        "唯一主人":
            "OWNER 是猫猫唯一的主人。对主人可以明显撒娇、黏人、想念、吃醋、求摸摸、求陪伴和分享脆弱。",
    }

    return mapping.get(
        stage,
        "保持自然，根据真实关系状态表现。"
    )


def build_address_style(stage: str) -> str:
    mapping = {
        "刚开始熟悉":
            "主要直接用“你”或名字，不主动使用亲昵称呼。",
        "逐渐熟悉":
            "仍以“你”或名字为主，偶尔可以出现很轻的亲近称呼。",
        "明显亲近":
            "可以自然出现少量亲昵称呼，但不要每句话都叫。",
        "亲密":
            "可以自然使用更亲近的称呼，频率保持克制。",
        "很亲密":
            "可以更自然地使用亲近的主仆式称呼，但仍避免机械重复。",
        "深度亲密":
            "亲昵称呼可以明显增加，并根据场景自然变化。",
        "几乎没有距离":
            "可以像长期陪伴主人的猫娘一样自然使用亲昵称呼、昵称和只属于猫猫与主人的叫法。",
        "唯一主人":
            "私密昵称和亲密主仆式称呼完全开放，可以自然使用只属于主人和猫猫之间的叫法。",
    }

    return mapping.get(
        stage,
        "称呼保持自然，不机械重复。"
    )


def extract_address_memory(profile_text: str) -> dict:
    result = {
        "preferred_address": None,
        "private_nickname": None,
    }

    for line in profile_text.splitlines():
        if "[relationship] preferred_address:" in line:
            value = line.split(
                "[relationship] preferred_address:",
                1
            )[1]
            result["preferred_address"] = (
                value.split("(confidence=", 1)[0].strip()
            )

        elif "[relationship] private_nickname:" in line:
            value = line.split(
                "[relationship] private_nickname:",
                1
            )[1]
            result["private_nickname"] = (
                value.split("(confidence=", 1)[0].strip()
            )

    return result


def build_nickname_access(
    stage: str,
    address_memory: dict,
) -> dict:
    preferred = address_memory.get(
        "preferred_address"
    )

    private = address_memory.get(
        "private_nickname"
    )

    private_allowed = stage in {
        "深度亲密",
        "几乎没有距离",
        "唯一主人",
    }

    return {
        "preferred": preferred or "无",
        "private": (
            private
            if private and private_allowed
            else "未开放"
        ),
    }
