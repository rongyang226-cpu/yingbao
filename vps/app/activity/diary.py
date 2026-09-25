from pathlib import Path
from datetime import datetime, timezone, timedelta

DIARY_PATH = Path(
    "/opt/ying/data/telegram/diary/ying_diary.md"
)

TZ = timezone(timedelta(hours=8))


def write_diary(
    content: str,
    mood: str | None = None,
    title: str | None = None,
):
    content = (content or "").strip()

    if not content:
        return False

    now = datetime.now(TZ)

    if not title:
        title = now.strftime("%Y-%m-%d")

    lines = [
        "",
        f"## {title}",
        f"- 时间：{now.strftime('%Y-%m-%d %H:%M')}",
    ]

    if mood:
        lines.append(f"- 心情：{mood}")

    lines += [
        "",
        content,
        "",
        "---",
        "",
    ]

    DIARY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with DIARY_PATH.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write("\n".join(lines))

    return True


def read_diary(
    max_chars: int = 8000,
) -> str:
    if not DIARY_PATH.exists():
        return ""

    text = DIARY_PATH.read_text(
        encoding="utf-8",
    )

    if len(text) > max_chars:
        text = text[-max_chars:]

    return text


def write_daily_summary(
    summary: str,
    mood: str | None = None,
):
    summary = (summary or "").strip()

    if not summary:
        return False

    now = datetime.now(TZ)

    return write_diary(
        content=summary,
        mood=mood,
        title=f"{now.strftime('%Y-%m-%d')} 今日总结",
    )


def build_today_diary_source() -> str:
    """
    给每日私人总结提供真实事实素材。
    这里只整理 life_log，不生成不存在的经历。
    """
    from app.activity.life_log import read_today_life_log

    items = read_today_life_log()

    if not items:
        return ""

    lines = []

    for item in items:
        time_text = str(
            item.get("time") or ""
        )

        if len(time_text) >= 16:
            time_text = time_text[11:16]
        else:
            time_text = "时间未知"

        activity = (
            item.get("activity")
            or ""
        )

        event = (
            item.get("event")
            or ""
        )

        detail = (
            item.get("detail")
            or ""
        ).strip()

        mood = (
            item.get("mood")
            or ""
        ).strip()

        thought = (
            item.get("thought")
            or ""
        ).strip()

        parts = [
            f"[{time_text}]"
        ]

        if activity:
            parts.append(
                f"活动={activity}"
            )

        if event:
            parts.append(
                f"事件={event}"
            )

        if detail:
            parts.append(
                f"事实={detail}"
            )

        if mood:
            parts.append(
                f"心情={mood}"
            )

        if thought:
            parts.append(
                f"当时碎碎念={thought}"
            )

        lines.append(
            "；".join(parts)
        )

    return "\n".join(lines)


async def generate_daily_diary():
    """
    根据当天真实 life_log 生成一篇萤的第一人称私人日记。
    同一天只生成一次正式总结。
    """
    from app.brain.deepseek import chat

    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    title = f"{today} 今日总结"

    # 防止同一天重复生成正式总结
    if DIARY_PATH.exists():
        old_text = DIARY_PATH.read_text(
            encoding="utf-8"
        )

        if f"## {title}" in old_text:
            return {
                "ok": False,
                "reason": "already_exists",
                "date": today,
            }

    source = build_today_diary_source()

    if not source.strip():
        return {
            "ok": False,
            "reason": "no_source",
            "date": today,
        }

    system_prompt = """
你是“萤”。

你正在写只属于自己的私人日记。

要求：
1. 必须使用第一人称“我”。
2. 只允许根据提供的【今日真实记录】写今天发生过的事情。
3. 不得创造记录里不存在的新事件、人物互动、聊天、地点移动、游戏结果或具体经历。
4. 可以根据记录里已经存在的心情、碎碎念和事实，写自己的主观感受。
5. 如果某条记录信息不完整，就保持模糊，不要自行补全。
6. 不得自行补充事件发生的原因、动作或过程。例如记录只写“掉下去了”，就不能擅自写成“手滑了”“没按准”“被打断了”等。
7. 可以写愿望、感想和对明天的期待，但必须明确属于主观想法，不能写成已经发生的事实。
8. 不要把程序字段、activity、event、mode 等技术词写进日记。
7. 不要写成工作总结、数据报告或流水账。
8. 语气自然、私人、生活化，像一个真实的人晚上写给自己看的日记。
9. 可以有一点碎碎念、懒散、开心、不爽、得意等情绪，但不要强行煽情。
10. 不要提到“根据记录”“系统显示”“数据库”等。
11. 不要写标题，只输出正文。
12. 长度控制在约200到500字。
""".strip()

    user_text = (
        "【今日真实记录】\n"
        + source
        + "\n\n"
        + "请根据以上内容写今天的私人日记。"
    )

    result = await chat(
        system_prompt=system_prompt,
        history=[],
        user_text=user_text,
        max_tokens=700,
    )

    result = (result or "").strip()

    if not result:
        return {
            "ok": False,
            "reason": "empty_result",
            "date": today,
        }

    write_diary(
        content=result,
        title=title,
    )

    return {
        "ok": True,
        "date": today,
        "content": result,
    }


def read_today_daily_diary() -> str:
    """读取今天的正式日记总结。"""
    import re

    if not DIARY_PATH.exists():
        return ""

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    title = f"{today} 今日总结"

    text = DIARY_PATH.read_text(
        encoding="utf-8"
    )

    pattern = (
        rf"## {re.escape(title)}\n"
        rf"(.*?)(?=\n## |\Z)"
    )

    match = re.search(
        pattern,
        text,
        flags=re.S,
    )

    if not match:
        return ""

    body = match.group(1).strip()

    # 给 OWNER 看时去掉文件分隔符
    body = body.removesuffix("---").strip()

    return body
