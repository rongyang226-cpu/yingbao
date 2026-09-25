
import aiosqlite

from app.config import DB_PATH


async def get_recent_entertainment_context():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                activity,
                game_name,
                mode,
                detail,
                duration_minutes,
                ended_at
            FROM activity_history
            WHERE activity='gaming'
            ORDER BY id DESC
            LIMIT 1
            """
        )

        row = await cur.fetchone()

    if not row:
        return ""

    (
        activity,
        game_name,
        mode,
        detail,
        duration_minutes,
        ended_at,
    ) = row

    if not detail:
        return ""

    lines = [
        "",
        "【最近娱乐经历】",
        f"- 类型: {mode}",
        f"- 游戏/娱乐: {game_name or '未知'}",
    ]

    if duration_minutes is not None:
        lines.append(
            f"- 持续约: {float(duration_minutes):.0f}分钟"
        )

    lines.append(
        f"- 真实记录: {detail}"
    )

    if mode == "real":
        lines.append(
            "- 这是实际运行产生的真实游戏结果，可以自然提起。"
        )

    elif mode == "simulated":
        lines.append(
            "- 这是模拟娱乐，不能描述成真实运行过该游戏。"
        )

    elif mode == "media":
        lines.append(
            "- 这是刷视频/摸鱼类娱乐；若没有实际搜索结果，不得编造具体看过的视频。"
        )

    lines.append(
        "- 可以自然表现对应情绪，比如生气、得意、委屈、吐槽、告状，也可以自然使用颜文字。"
    )

    return "\n".join(lines)
