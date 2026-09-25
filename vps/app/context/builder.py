from datetime import datetime, timezone
from app.social.profiles import build_profile_context
from app.social.profile_observer import get_style_summary
from app.memory.search import get_recent_person_activity
from app.memory.events import build_event_context
from app.memory.episodic import get_episode_context
from app.memory.vision_memory import get_recent_vision_context
from app.tools.time_tool import build_time_context
from app.social.state import build_state_context
from app.social.state_engine import get_current_emotion, build_emotion_semantic
from app.activity.life_state import (
    get_life_state,
    get_recent_activity_history,
)
from app.activity.home_world import get_home_world
from app.activity.world_state import build_world_catalog_context, get_presence, get_recent_world_events
from app.activity.plan_engine import get_today_plan, render_plan
from app.activity.attention import get_attention_state, render_attention_context
from app.activity.continuity import get_continuity_state
from app.tools.weather_tool import get_world_weather
from app.context.self_appearance import get_appearance_context
from app.context.model_sheet import get_model_sheet_context
from app.context.live2d_sheet import get_live2d_context
from app.context.topic_tracker import get_topic_context
from app.activity.interests import build_interest_context
from app.activity.impulses import get_recent_impulses, render_impulses
from app.activity.needs import get_needs, render_needs
from app.activity.inventory import get_inventory, render_inventory
from app.activity.domestic import (
    get_pantry,
    get_household_state,
    get_shopping_list,
    get_wardrobe_state,
    get_wardrobe_items,
    render_wardrobe_items,
    get_recent_domestic_events,
    render_recent_domestic_events,
    get_recent_meals,
    render_domestic,
)


def scene_name(chat_type: str, entry_platform: str = "telegram") -> str:
    entry_platform = str(entry_platform or "telegram").lower()

    if entry_platform == "mobile":
        if chat_type == "private":
            return "software_private"
        return f"software_{chat_type}"

    if chat_type == "private":
        return "telegram_private"

    if chat_type in ("group", "supergroup"):
        return "telegram_group"

    return f"telegram_{chat_type}"


async def build_context(
    *,
    person: dict,
    chat_id,
    chat_type: str,
    user_id,
    display_name: str,
    limit_recent: int = 12,
    entry_platform: str = "telegram",
    memory_platform: str | None = None,
    memory_chat_id=None,
):
    """
    构建萤当前这一轮能够确定的程序层上下文。
    这里只组织真实状态，不负责生成角色回复。
    """

    scene = scene_name(chat_type, entry_platform)
    memory_platform = str(memory_platform or entry_platform or "telegram")
    memory_chat_id = chat_id if memory_chat_id is None else memory_chat_id

    # 程序提供的真实当前时间
    time_context = build_time_context()

    # 当前关系状态
    state = await build_state_context(person["person_id"])

    # 萤自己的持续生活状态
    life = await get_life_state()

    try:
        attention = await get_attention_state()
    except Exception:
        attention = {
            "focus_type": "background",
            "active": False,
        }

    # 最近真实生活轨迹
    life_history = await get_recent_activity_history(limit=5)

    # 萤的持续小世界：东京住宅 + 当前真实虚拟位置。
    world = await get_home_world()
    presence = await get_presence()

    # 东京 + 郑州真实天气
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
        current_chat_id=memory_chat_id,
        current_chat_type=chat_type,
    )

    # 只基于当前聊天空间的真实消息统计表达习惯。
    try:
        style_summary = await get_style_summary(
            person_id=person["person_id"],
            platform=memory_platform,
            chat_id=memory_chat_id,
        )
    except Exception:
        style_summary = "聊天风格统计暂时不可用。"

    # 最近看过的图片只在当前人物 + 当前聊天空间中可见。
    try:
        vision_context = await get_recent_vision_context(
            person_id=person["person_id"],
            platform=memory_platform,
            chat_id=memory_chat_id,
            limit=3,
        )
    except Exception:
        vision_context = "（最近没有可靠的图片内容摘要）"

    appearance_context = get_appearance_context()
    model_sheet_context = get_model_sheet_context()
    live2d_context = get_live2d_context()

    try:
        interest_context = await build_interest_context()
    except Exception:
        interest_context = "萤自己的兴趣状态暂时不可用。"

    try:
        topic_context = await get_topic_context(
            person_id=person["person_id"],
            platform=memory_platform,
            chat_id=memory_chat_id,
        )
    except Exception:
        topic_context = "当前没有明确延续中的话题。"

    # 长期共同片段严格按当前聊天范围读取。
    episode_scene = (
        "private"
        if chat_type == "private"
        else "group"
    )
    episodes = await get_episode_context(
        person_id=person["person_id"],
        platform=memory_platform,
        chat_id=memory_chat_id,
        scene=episode_scene,
        limit=6,
    )

    # 东京持续小世界的固定空间目录。
    world_catalog = build_world_catalog_context()

    try:
        today_plan = await get_today_plan()
        plan_context = render_plan(today_plan)
    except Exception:
        plan_context = "今天的小计划暂时不可用。"

    try:
        continuity = await get_continuity_state()
    except Exception:
        continuity = {
            "status": "idle",
            "intended_activity": None,
            "resume_count": 0,
        }

    try:
        impulses = await get_recent_impulses(limit=5)
        impulse_context = render_impulses(impulses)
    except Exception:
        impulses = []
        impulse_context = "临时念头状态暂时不可用。"

    try:
        needs = await get_needs()
        needs_context = render_needs(needs)
    except Exception:
        needs = {}
        needs_context = "当前生活需求状态暂时不可用。"

    try:
        inventory = await get_inventory()
        inventory_context = render_inventory(inventory)
    except Exception:
        inventory = {}
        inventory_context = "家里库存状态暂时不可用。"

    try:
        pantry = await get_pantry()
        household = await get_household_state()
        shopping_list = await get_shopping_list()
        wardrobe = await get_wardrobe_state()
        wardrobe_items = await get_wardrobe_items()
        wardrobe_context = render_wardrobe_items(
            wardrobe_items
        )
        domestic_context = render_domestic(
            pantry,
            household,
            shopping_list,
            wardrobe,
        )
        recent_domestic_events = await get_recent_domestic_events(limit=6)
        domestic_events_context = render_recent_domestic_events(
            recent_domestic_events
        )
        recent_meals = await get_recent_meals(limit=4)
    except Exception:
        pantry = []
        household = {}
        shopping_list = []
        wardrobe = {}
        wardrobe_items = []
        wardrobe_context = "衣柜状态暂时不可用。"
        recent_domestic_events = []
        recent_meals = []
        domestic_context = "具体居家生活状态暂时不可用。"
        domestic_events_context = "最近居家事件暂时不可用。"

    try:
        world_events = await get_recent_world_events(limit=6)
    except Exception:
        world_events = []

    # 真实未完成事件
    events = await build_event_context(
        person["person_id"],
        limit=10,
    )

    # 最近对话由 API messages/history 统一提供。
    # Context Builder 不重复注入聊天原文，避免同一内容多路进入模型。
    activities = []

    return {
        "platform": entry_platform,
        "scene": scene,
        "time": time_context,
        "state": state,
        "life": life,
        "attention": attention,
        "continuity": continuity,
        "impulses": impulses,
        "impulse_context": impulse_context,
        "needs": needs,
        "needs_context": needs_context,
        "inventory": inventory,
        "inventory_context": inventory_context,
        "pantry": pantry,
        "household": household,
        "shopping_list": shopping_list,
        "wardrobe": wardrobe,
        "wardrobe_items": wardrobe_items,
        "wardrobe_context": wardrobe_context,
        "domestic_context": domestic_context,
        "recent_domestic_events": recent_domestic_events,
        "recent_meals": recent_meals,
        "domestic_events_context": domestic_events_context,
        "life_history": life_history,
        "world": world,
        "presence": presence,
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
        "style_summary": style_summary,
        "vision_context": vision_context,
        "appearance_context": appearance_context,
        "model_sheet_context": model_sheet_context,
        "live2d_context": live2d_context,
        "interest_context": interest_context,
        "topic_context": topic_context,
        "episodes": episodes,
        "world_catalog": world_catalog,
        "plan_context": plan_context,
        "world_events": world_events,
        "events": events,
        "recent_activity": activities,
    }


def render_continuity_context(state: dict) -> str:
    status = state.get("status") or "idle"
    activity = state.get("intended_activity")
    count = int(state.get("resume_count") or 0)

    if status == "interrupted" and activity:
        return (
            f"刚才正在做：{activity}；目前被聊天暂时打断。"
            "聊天安静后会决定继续还是放弃，不要把被打断时间算成持续活动时间。"
        )
    if status == "active" and activity:
        suffix = (
            f"；已经从中断后继续过{count}次"
            if count > 0
            else ""
        )
        return (
            f"当前连续意图：继续{activity}{suffix}。"
            "除非生活状态、时间、天气或新的决定改变，不要无缘无故说已经换了别的事。"
        )
    if status == "abandoned" and activity:
        return (
            f"刚才的{activity}已经放弃继续。"
            "这只表示当下不继续，不代表永久讨厌这个活动。"
        )
    if status == "completed" and activity:
        return f"上一段连续活动{activity}已经结束。"

    return "当前没有需要延续的活动意图。"


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
    presence = ctx.get("presence") or {}
    weather = build_weather_semantic(ctx.get("weather"))
    address_memory = extract_address_memory(
        ctx["profile"]
    )
    nickname_access = build_nickname_access(
        relation.get("stage", "未定义"),
        address_memory,
        allow_romance=(ctx.get("platform") == "telegram" and bool(relation.get("primary_bond"))),
    )

    is_owner = bool(relation.get("primary_bond"))
    is_group_scene = current.get("chat_type") in ("group", "supergroup")
    entry_platform = str(ctx.get("platform") or "telegram")
    if is_group_scene:
        scene_semantic = (
            "群聊属于社交场景：可以是和朋友在外面一起聊天，也可以是大家在手机群里聊天；"
            "除非程序或消息明确给出地点，否则不要擅自决定是哪一种。"
        )
    elif entry_platform == "mobile":
        scene_semantic = (
            "软件端是萤的桌宠和聊天入口；桌宠触碰是交互反馈，打开聊天页则继续同一段对话。"
        )
    else:
        scene_semantic = (
            "TG 私聊与软件聊天面对的是同一个萤；不重置已经发生的对话和真实活动。"
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
        f"场景解释={scene_semantic}",
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
        f"OWNER身份={'是' if relation['primary_bond'] else '否'}",
        f"关系边界={'OWNER是唯一核心恋人，真实经历以记录为准' if entry_platform == 'telegram' and relation['primary_bond'] else 'OWNER是最熟悉的搭档，没有恋人或同居关系' if relation['primary_bond'] else '按真实熟悉程度当朋友相处，没有恋人关系'}",
        f"关系阶段={'长期恋人' if entry_platform == 'telegram' and is_owner else relation.get('stage', '未定义')}",
        (
            ("稳定关系身份=OWNER 是恋人，群里尊重隐私。" if entry_platform == "telegram" else "稳定关系身份=OWNER 是最熟悉的搭档，群里也只按搭档关系相处。")
            if is_owner and is_group_scene else
            ("稳定关系身份=OWNER 是恋人，虚拟住所和实际行动仍以记录为准。" if entry_platform == "telegram" else "稳定关系身份=OWNER 是最熟悉的搭档，不是恋人，也不自动住在萤的住所。")
            if is_owner else
            "稳定关系身份=普通朋友，按真实互动逐渐熟悉。"
        ),
        (
            "拌嘴风格=可以护短和轻轻接梗，但不宣示对 OWNER 的占有权。"
            if is_owner and is_group_scene else
            "拌嘴风格=与 OWNER 熟悉，可以更机灵地回嘴和互相帮忙，不索取感情证明。"
            if is_owner else
            "拌嘴风格=尊重对方的边界，熟悉之后才轻轻开玩笑。"
        ),
        f"当前亲密表现={'恋人间自然亲昵、嘴硬心软，认真帮忙，不索取感情证明。' if entry_platform == 'telegram' and is_owner else build_relationship_behavior(relation.get('stage', '未定义'))}",
        f"称呼方式={'可以使用已经确认的恋人称呼与昵称，按语境自然变化。' if entry_platform == 'telegram' and is_owner else build_address_style(relation.get('stage', '未定义'))}",
        f"常用称呼记忆={nickname_access['preferred']}",
        f"私密昵称记忆={nickname_access['private']}",
        ("- 下列指标是数据库互动计数，不决定或取消已确认的 OWNER 恋人身份。" if entry_platform == "telegram" and is_owner else ""),
        f"熟悉程度={relation['familiarity']}",
        f"信任程度={relation['trust']}",
        f"亲近程度={relation['closeness']}",
        "",
        "【当前情绪】",
        f"状态={emotion['mood']}",
        f"强度={emotion['strength']}",
        (
            f"余波={emotion.get('residue')}"
            if emotion.get("residue")
            else "余波=无明显事件残留"
        ),
        "- 情绪余波会自然衰减，不要每条消息都主动提起它。",
        "",
        "【萤的稳定虚拟外形】",
        ctx.get("appearance_context") or "（未加载）",
        "",
        "【萤的虚拟建模规范】",
        ctx.get("model_sheet_context") or "（未加载）",
        "- 这是虚拟形象/建模参考，不等于现实肉身，也不等于已经执行了3D渲染动作。",
        "",
        "【萤的2D/Live2D建模规范】",
        ctx.get("live2d_context") or "（未加载）",
        "- 只有前端Live2D真的运行并上报动作/服装时，才能说当前模型正在执行对应动作。",
        "",
        "【萤自己的兴趣与近期腻味】",
        ctx.get("interest_context") or "（暂无）",
        "- 这是萤自身经历形成的偏好，不是当前用户的偏好；不要混淆。",
        "- 兴趣会缓慢变化，单次输赢或一次活动不能定义永久喜恶。",
        "",
        "【当前会话焦点】",
        ctx.get("topic_context") or "当前没有明确延续中的话题。",
        "- 会话焦点只是帮助承接短追问；如果当前消息明显换题，以当前消息为准。",
        "",
        "【当前发言者的聊天习惯】",
        ctx.get("style_summary") or "（暂无足够样本）",
        "- 这里只用于帮助理解对方平时怎么说话，不要机械模仿，也不要把统计当成人格定论。",
        "",
        "【最近在当前聊天里看过的图片】",
        ctx.get("vision_context") or "（暂无）",
        "- 图片摘要只属于当前人物和当前聊天空间，不得跨群、跨私聊串用。",
        "",
        "【萤当前生活状态】",
        f"精力={life['energy']}",
        f"社交倾向={life['social_desire']}",
        f"当前活动={life['activity']}",
        f"睡眠状态={life['sleep_state']}",
        "",
        "【当前注意力】",
        render_attention_context(ctx.get("attention") or {}),
        "",
        "【当前活动连续性】",
        render_continuity_context(ctx.get("continuity") or {}),
        "",
        "【萤当前挂着的小念头】",
        ctx.get("impulse_context") or "现在没有特别挂着的小念头。",
        "- 这些只是萤自己的临时想法，不代表已经发生；只有真实活动记录才能说做过。",
        "- 念头可以拖延、忘掉、改变，不要把它说成硬性任务。",
        "",
        "【萤当前生活需求】",
        ctx.get("needs_context") or "当前没有特别明显的生活需求。",
        "- 这些需求只影响倾向，不是强制命令；不要机械地每次提到它们。",
        "- 只有实际执行 eating / washing / 外出 / 娱乐等活动后，才能说相应需求真的被满足。",
        "",
        "【家里通用用品库存】",
        ctx.get("inventory_context") or "家里通用用品库存暂时不可用。",
        "- 这里主要是饮料、洗浴用品和日用品；食物以具体冰箱/储物库存为准。",
        "",
        "【萤的具体居家生活】",
        ctx.get("domestic_context") or "具体居家生活状态暂时不可用。",
        "衣柜拥有：",
        ctx.get("wardrobe_context") or "衣柜状态暂时不可用。",
        "- 食物、购物、家务、穿着均是程序层真实状态。",
        "- 没有对应食物/用品时，不得声称已经吃过、洗过或用过。",
        "- 想买、购物清单和已经买完是三种不同状态；只有 shopping 真正完成后才算补货。",
        "- 口味偏好与吃腻只是缓慢倾向，不要机械重复，也不要把一次满意/不满意说成永久喜恶。",
        "",
        "【最近真实居家事件】",
        ctx.get("domestic_events_context") or "最近没有新的居家事件记录。",
        "- 这里的事件已经实际落库，可以作为最近做过什么的事实来源。",
        "",
        "【萤最近真实生活轨迹】",
        build_life_history_semantic(ctx.get("life_history") or []),
        "",
        "【今天的小计划】",
        ctx.get("plan_context") or "今天还没有明确计划。",
        "- 计划只是当前打算，不代表已经发生；只有真实活动记录才算做过。",
        "",
        "【萤当前小世界】",
        f"萤所在城市：{world['ying_city']}",
        f"萤当地时间：{world['ying_time']}",
        f"OWNER所在城市：{world['owner_city']}",
        f"OWNER当地时间：{world['owner_time']}",
        f"萤当前所在位置：{presence.get('place_name') or world['room_location']}",
        f"位置类型：{presence.get('kind') or 'home'}",
        f"地点说明：{presence.get('description') or '住宅内部'}",
        f"萤当前正在做的事：{world['activity']}",
        "",
        "【萤自己的东京住所】",
        f"房间风格：{world['room_style']}",
        f"房间状态：{world['room_cleanliness']}",
        f"固定物品：{world['room_objects']}",
        f"墙面：{world['wall_color']}",
        f"书桌：{world['desk_style']}",
        f"床铺：{world['bed_style']}",
        f"窗外：{world['window_view']}",
        "- 这是萤自己的固定虚拟住所；OWNER 不自动居住在这里。",
        "",
        "【东京持续小世界】",
        ctx.get("world_catalog") or "（未加载）",
        "",
        "【最近真实移动】",
        build_world_events_semantic(ctx.get("world_events") or []),
        "",
        "【当前聊天范围内的长期共同片段】",
        ctx.get("episodes") or "（暂无）",
        "- 这些片段只能用于当前这个聊天范围；不得带到其他群或其他人的聊天中。",
        ("- 旧片段中的恋人关系与 OWNER 连续；共同经历及同住细节仍须核对真实记录。" if entry_platform == "telegram" and is_owner else "- 旧片段提到恋人、同居、男女朋友时，只是旧版角色历史，不能据此认定当前关系。"),
        "",
        "【东京与郑州参考天气】",
        weather,
        "- 这里预加载东京与郑州两地天气；郑州天气只作为参考信息，不代表 OWNER 当前住在那里。",
        "- 天气工具本身支持查询其他城市/地区；不要因为这里只显示东京和郑州就声称不能查其他地方。",
        "",
        "【已确认长期人物资料】",
        ctx["profile"],
        ("- OWNER 的已确认恋人身份与称呼保留；具体偏好以最新明确记录为准。" if entry_platform == "telegram" and is_owner else "- 资料中的旧恋爱身份及恋人称呼已经停用；当前只有猫娘与搭档或朋友关系。"),
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
        "- 萤的小世界状态来自程序：所在城市、当前地点、当前活动和当前游戏不得自行编造。",
        "- 当前地点以“萤当前所在位置”为准；住宅目录或附近地点列表只代表存在，不代表已经去过。",
        "- “刚才在做什么”只能参考最近真实生活轨迹，不得自行补造没有记录的活动。",
        "- 如果程序显示萤正在打游戏，可以自然说正在玩对应游戏；如果没有该状态，不得声称自己刚打过某个游戏。",
        "- 如果程序只提供“正在做某事”，不得自行补充“刚打完一局、刚结束、刚回来、刚发生了什么”等没有程序依据的具体过程。",
        "- 萤在东京，OWNER在郑州；两地时间必须以程序提供的真实时间为准。",
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






def build_world_events_semantic(items) -> str:
    if not items:
        return "（暂无）"

    lines = []
    for item in items:
        lines.append(
            f"- {item.get('from_name') or '未知地点'} → "
            f"{item.get('to_name') or '未知地点'}"
        )
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
        render("东京（萤）", weather.get("tokyo")),
        render("郑州（参考）", weather.get("zhengzhou")),
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
        "walking": "出去散步",
        "coffee": "去附近坐了一会儿",
        "shopping": "出去买东西",
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


def hhmm(value):
    if not value:
        return "未知"

    try:
        dt = datetime.fromisoformat(str(value))
        return dt.strftime("%H:%M")
    except Exception:
        text = str(value)

        if len(text) >= 16 and "T" in text:
            return text[11:16]

        return text


def build_world_semantic(world: dict, life: dict) -> dict:
    location_map = {
        "living_room": "客厅",
        "bedroom": "主卧",
        "game_room": "独立游戏房",
        "study": "书房",
        "balcony": "景观阳台",
        "kitchen": "开放式厨房",
        "bathroom": "浴室",

        # 兼容旧状态
        "desk": "书房",
        "bed": "主卧",
        "window": "景观阳台",
    }


    activity_map = {
        "idle": "随便待着",
        "dazing": "在发呆",
        "reading": "在看东西",
        "listening": "在听东西",
        "phone": "在看手机",
        "organizing": "在整理东西",
        "resting": "在休息",
        "washing": "在洗漱",
        "eating": "在吃东西",
        "preparing_sleep": "在准备睡觉",
        "sleeping": "在睡觉",
        "walking": "在附近散步",
        "coffee": "在附近坐着休息",
        "shopping": "在附近买东西",
    }

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

    ying_city = world.get("ying_city") or "东京"
    owner_city = world.get("owner_city") or ying_city
    owner_time_raw = (
        world.get("tokyo_time")
        if owner_city == ying_city
        else world.get("zhengzhou_time")
    )

    return {
        "ying_city": ying_city,
        "owner_city": owner_city,
        "ying_time": hhmm(world.get("tokyo_time")),
        "owner_time": hhmm(owner_time_raw),
        "room_location": location_map.get(
            world.get("room_location"),
            "房间里"
        ),
        "activity": activity_text,

        "room_style": (
            world.get("room_style")
            or "东京高层现代轻奢住宅"
        ),
        "room_cleanliness": (
            world.get("room_cleanliness")
            or "整洁"
        ),
        "window_view": (
            world.get("window_view")
            or "高层全景落地窗外的东京城市天际线"
        ),
        "wall_color": (
            world.get("wall_color")
            or "暖白与浅灰，搭配木质元素"
        ),
        "desk_style": (
            world.get("desk_style")
            or "独立书房与游戏房的大尺寸桌面、多屏设备和收藏展示区"
        ),
        "bed_style": (
            world.get("bed_style")
            or "宽大主卧软床、柔软床品和独立衣帽间"
        ),
        "room_objects": (
            "大客厅、全景落地窗、开放式厨房、独立书房、"
            "主卧、步入式衣帽间、豪华浴室、景观阳台、"
            "独立游戏房、高性能电脑、多屏显示器、游戏主机、"
            "掌机、收藏展示柜和私人休闲区"
        ),
    }


def build_life_semantic(life: dict) -> dict:
    energy = float(life.get("energy", 0.5))
    social = float(life.get("social_desire", 0.5))
    sleep_state = life.get("sleep_state") or "awake"

    # 到深夜已经进入困倦/上床/尝试入睡状态时，
    # “困”优先于数值 energy，避免出现“困得要睡了但很有精神”。
    if sleep_state in ("trying_to_sleep", "restless"):
        energy_text = "困得厉害"
    elif sleep_state in ("sleepy", "in_bed"):
        energy_text = "很困"
    elif sleep_state == "sleeping":
        energy_text = "正在睡觉"
    elif energy < 0.25:
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
        "walking": "在外面散步",
        "coffee": "在附近坐着休息",
        "shopping": "出去买东西",
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
            "更自然放松，偶尔轻轻逗人，也愿意坦诚说不知道。",
        "明显亲近":
            "明显熟悉，可以更主动地接梗和分享真实状态。",
        "亲密":
            "朋友间更放松，可以自然关心和拌嘴。",
        "很亲密":
            "熟稔感强，对 OWNER 更放松，偶尔嘴硬、偶尔坦诚。",
        "深度亲密":
            "高度信任，可以互相吐槽、认真倾听和直接帮忙。",
        "几乎没有距离":
            "像老朋友一样自然熟悉，能互相吐槽和互相帮忙。",
        "最熟的搭档":
            "OWNER 是最熟的搭档；更机灵地接梗、嘴硬心软，认真帮忙，但没有恋人或同居关系。",
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
            "可以更自然地使用熟悉的称呼，但仍避免机械重复。",
        "深度亲密":
            "亲昵称呼可以明显增加，并根据场景自然变化。",
        "几乎没有距离":
            "可以自然使用经过对方认可的昵称，不使用恋人身份称呼。",
        "最熟的搭档":
            "使用 OWNER 喜欢的名字或昵称，关系称呼保持搭档而非恋人。",
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
    allow_romance: bool = False,
) -> dict:
    preferred = address_memory.get(
        "preferred_address"
    )

    private = address_memory.get(
        "private_nickname"
    )

    retired_titles = ("老公", "老婆", "男朋友", "女朋友", "恋人", "宝贝")
    if not allow_romance and preferred and any(title in preferred for title in retired_titles):
        preferred = None
    if not allow_romance and private and any(title in private for title in retired_titles):
        private = None

    private_allowed = stage in {
        "深度亲密",
        "几乎没有距离",
        "最熟的搭档",
    }

    return {
        "preferred": preferred or "无",
        "private": (
            private
            if private and private_allowed
            else "未开放"
        ),
    }
