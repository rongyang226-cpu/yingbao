"""TG 与手机端共用的中文指令说明。"""

COMMAND_MANUAL_VERSION = "1.0"


COMMANDS = [
    {"name": "/start", "title": "开始", "category": "基础", "description": "启动萤并显示简要入口。", "platforms": ["telegram", "mobile"], "owner": False, "usage": "/start"},
    {"name": "/help", "title": "帮助", "category": "基础", "description": "查看常用指令；/help all 查看全部，/help 指令名 查看详细说明。", "platforms": ["telegram", "mobile"], "owner": False, "usage": "/help [all|指令名]"},
    {"name": "/commands", "title": "全部指令", "category": "基础", "description": "打开完整指令表，是 /help all 的快捷入口。", "platforms": ["telegram", "mobile"], "owner": False, "usage": "/commands"},
    {"name": "/status", "title": "状态", "category": "基础", "description": "查看萤自身状态、活动、心情、精力、位置、穿着以及双时区时间。", "platforms": ["telegram", "mobile"], "owner": True, "usage": "/status"},
    {"name": "/time", "title": "时间", "category": "基础", "description": "同时查看萤所在地时间和北京时间。", "platforms": ["telegram", "mobile"], "owner": False, "usage": "/time"},
    {"name": "/me", "title": "我的身份", "category": "基础", "description": "查看当前平台识别到的身份与权限。", "platforms": ["telegram", "mobile"], "owner": False, "usage": "/me"},
    {"name": "/version", "title": "版本", "category": "基础", "description": "查看统一指令集版本与当前入口。", "platforms": ["telegram", "mobile"], "owner": False, "usage": "/version"},
    {"name": "/reset", "title": "清当前聊天", "category": "聊天", "description": "只清当前私聊消息记录，不删除长期记忆，也不碰其他平台或群聊。", "platforms": ["telegram", "mobile"], "owner": False, "usage": "/reset"},
    {"name": "/private", "title": "隐私模式", "category": "隐私", "description": "OWNER 管理 TG 私聊隐私：status / on / strict / off。", "platforms": ["telegram"], "owner": True, "usage": "/private status|on|strict|off"},
    {"name": "/chess", "title": "国际象棋", "category": "游戏", "description": "在 TG 私聊里与萤开始一盘真实国际象棋。", "platforms": ["telegram"], "owner": False, "usage": "/chess"},
    {"name": "/chess_status", "title": "棋局状态", "category": "游戏", "description": "查看当前国际象棋棋局。", "platforms": ["telegram"], "owner": False, "usage": "/chess_status"},
    {"name": "/chess_stop", "title": "结束棋局", "category": "游戏", "description": "结束当前国际象棋棋局。", "platforms": ["telegram"], "owner": False, "usage": "/chess_stop"},
    {"name": "/debug", "title": "调试信息", "category": "系统", "description": "OWNER 查看 TG 机器人调试信息。", "platforms": ["telegram"], "owner": True, "usage": "/debug"},
]

APP_FEATURES = [
    {"title": "聊天", "description": "打开萤的完整聊天页面。"},
    {"title": "人物姿态", "description": "手动切换人物动作与站姿。"},
    {"title": "衣柜", "description": "切换固定服装并同步到 VPS。"},
    {"title": "触碰互动", "description": "点击不同部位触发不同回应。"},
    {"title": "悬浮窗", "description": "打开或收起桌面精灵。"},
    {"title": "生活状态", "description": "查看活动、心情、精力和位置。"},
    {"title": "详细日志", "description": "查看生活、游戏、接口和错误记录。"},
    {"title": "真实游戏", "description": "从软件进入 VPS 上的 2048、五子棋等真实游戏。"},
]


def _visible(platform: str, owner: bool) -> list[dict]:
    platform = str(platform or "").lower()
    return [
        item for item in COMMANDS
        if platform in item["platforms"] and (owner or not item["owner"])
    ]


def command_detail(platform: str, owner: bool, query: str) -> str | None:
    key = str(query or "").strip().lower()
    if not key:
        return None
    if not key.startswith("/"):
        key = "/" + key
    item = next((x for x in _visible(platform, owner) if x["name"] == key), None)
    if not item:
        return None
    support = "、".join("TG" if x == "telegram" else "软件" for x in item["platforms"])
    permission = "仅 OWNER" if item["owner"] else "当前用户可用"
    return "\n".join([
        f'{item["name"]} · {item["title"]}',
        "",
        f'用法：{item["usage"]}',
        f'作用：{item["description"]}',
        f'权限：{permission}',
        f'支持：{support}',
    ])


def help_text(platform: str, owner: bool = False, query: str | None = None, full: bool = False) -> str:
    q = str(query or "").strip().lower()
    if q in {"all", "全部", "所有"}:
        full = True
        q = ""
    if q:
        detail = command_detail(platform, owner, q)
        return detail or "没找到这条指令。发 /commands 看完整指令表。"
    items = _visible(platform, owner)
    if not full:
        common = {"/help", "/commands", "/status", "/time", "/me", "/reset"}
        if platform == "telegram":
            common |= {"/chess", "/chess_status", "/chess_stop"}
            if owner:
                common |= {"/private"}
        items = [x for x in items if x["name"] in common]
    title = "萤 · 完整指令表" if full else "萤 · 常用指令"
    lines = [title, f"指令集 v{COMMAND_MANUAL_VERSION}", ""]
    last_category = None
    for item in items:
        if full and item["category"] != last_category:
            if last_category is not None:
                lines.append("")
            last_category = item["category"]
            lines.append(f'【{last_category}】')
        lines.append(f'{item["usage"]}  {item["title"]}')
    lines += [
        "",
        "发送 /help 指令名 可看详细说明。",
        "发送 /commands 可看全部指令。",
        "自然语言也能正常聊天，不需要每次都敲指令。",
    ]
    return "\n".join(lines)


def commands_payload(platform: str, owner: bool = False) -> dict:
    return {
        "ok": True,
        "version": COMMAND_MANUAL_VERSION,
        "platform": platform,
        "commands": _visible(platform, owner),
        "app_features": APP_FEATURES if platform == "mobile" else [],
        "notes": [
            "/reset 只清当前私聊，不删除长期记忆。",
            "软件按钮和 TG 指令共用同一套说明源。",
            "不知道命令时直接发 /commands 或 /help 指令名。",
        ],
    }
