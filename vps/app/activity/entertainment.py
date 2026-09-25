
import asyncio
import random
from pathlib import Path

from games.real.chess_game import play_game as play_chess
from games.real.game2048 import play_game as play_2048
from games.real.gomoku import play_game as play_gomoku
from games.real.jump_jump import play_game as play_jump_jump
from games.real.match3 import play_game as play_match3
from games.real.go_game import play_game as play_go
from app.activity.interests import weighted_choice, record_interest_event


REAL_GAMES = (
    "2048",
    "chess",
    "gomoku",
    "jump_jump",
    "match3",
    "go",
)

def _2048_reaction(result):
    tile = int(result.get("max_tile") or 0)
    score = int(result.get("score") or 0)

    if tile >= 2048:
        mood = "excited"
        texts = [
            f"真让我合到2048了！分数{score}，哼哼，我还是很厉害的嘛 (≧▽≦)",
            f"2048！看到了没，我打出来的！(๑•̀ㅂ•́)و✧",
        ]

    elif tile >= 512:
        mood = "happy"
        texts = [
            f"这局最高都到{tile}了，还不错吧～",
            f"最高{tile}，差一点还能继续冲，我感觉这把挺顺的 (´▽｀)",
        ]

    elif tile >= 256:
        mood = "annoyed"
        texts = [
            f"最高才{tile}……明明中间有几步挺好的，后面给我堵死了 (｀へ´)",
            f"这破棋盘最后挤得一点地方都没有，最高{tile}，气。",
        ]

    else:
        mood = "frustrated"
        texts = [
            f"最高才{tile}……不许笑我！这局后面完全没地方挪了 (╯°□°）╯︵ ┻━┻",
            f"我跟你告状，这局2048故意针对我。最高才{tile}，烦死了 (｀へ´)",
        ]

    return mood, random.choice(texts)


def _chess_reaction(result):
    outcome = result.get("result", "*")
    moves = int(result.get("move_count") or 0)

    if outcome == "1-0":
        mood = "proud"
        texts = [
            f"下完了，白方赢，整整{moves}手。这个可以夸一下吧 (￣▽￣)",
            f"{moves}手，1-0。赢了～我先得意一会儿。",
        ]

    elif outcome == "0-1":
        mood = "proud"
        texts = [
            f"黑方赢了，{moves}手结束。嘿嘿，这盘挺漂亮。",
            f"{moves}手，0-1，黑方拿下 (๑•̀ㅂ•́)و✧",
        ]

    elif outcome == "1/2-1/2":
        mood = "mixed"
        texts = [
            f"这盘下了{moves}手，最后和棋。谁也不肯让步是吧 (｀・ω・´)",
            f"这盘下了{moves}手最后和棋……下得够久的，我脑子都快冒烟了。",
        ]

    else:
        mood = "confused"
        texts = [
            f"这盘走了{moves}手还没正常结束，先记下来，不能算我赢也不能算我输。",
        ]

    return mood, random.choice(texts)


def _last_real_game():
    session_dir = Path("/opt/ying/games/sessions")
    files = sorted(
        session_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None

    name = files[0].name
    for game in REAL_GAMES:
        prefix = {
            "2048": "2048_",
            "chess": "chess_",
            "gomoku": "gomoku_",
            "jump_jump": "jump_jump_",
            "match3": "match3_",
            "go": "go_",
        }[game]
        if name.startswith(prefix):
            return game

    return None


async def play_real_game(game=None):
    if game is None:
        previous = _last_real_game()
        pool = [g for g in REAL_GAMES if g != previous]
        game = await weighted_choice(
            "game",
            pool or list(REAL_GAMES),
        )

    if game == "2048":
        result = await asyncio.to_thread(play_2048)
        mood, reaction = _2048_reaction(result)

    elif game == "chess":
        result = await asyncio.to_thread(play_chess)
        mood, reaction = _chess_reaction(result)

    elif game == "gomoku":
        result = await asyncio.to_thread(play_gomoku)

        winner = result.get("winner", "draw")
        moves = int(result.get("move_count") or 0)

        if winner == "black":
            winner_text = "黑方"
            mood = "happy"
        elif winner == "white":
            winner_text = "白方"
            mood = "happy"
        else:
            winner_text = "和棋"
            mood = "mixed"

        reaction = (
            f"五子棋下了{moves}手，"
            f"最后是{winner_text}。"
        )

    elif game == "jump_jump":
        result = await asyncio.to_thread(play_jump_jump)

        score = int(result.get("score") or 0)

        if score >= 30:
            mood = "proud"
            reaction = f"跳一跳打到{score}分才掉，嘿嘿。"
        elif score >= 10:
            mood = "happy"
            reaction = f"跳一跳这把{score}分，还行。"
        else:
            mood = "annoyed"
            reaction = f"跳一跳才{score}分就掉了……气。"

    elif game == "match3":
        result = await asyncio.to_thread(play_match3)

        score = int(result.get("score") or 0)
        moves = int(result.get("move_count") or 0)

        if score >= 6000:
            mood = "proud"
        elif score >= 4000:
            mood = "happy"
        else:
            mood = "mixed"

        reaction = (
            f"三消玩了{moves}步，"
            f"最后{score}分。"
        )

    elif game == "go":
        result = await asyncio.to_thread(play_go)

        winner = result.get("winner")
        score = result.get("final_score") or "未知"
        moves = int(result.get("move_count") or 0)

        if winner in ("black", "white"):
            mood = "focused"
            side = "黑方" if winner == "black" else "白方"
            reaction = (
                f"围棋下完了，{moves}手，"
                f"{side}赢，终局{score}。"
            )
        elif winner == "draw":
            mood = "mixed"
            reaction = (
                f"围棋下了{moves}手，最后和棋。"
            )
        else:
            mood = "confused"
            reaction = (
                f"围棋实际跑了{moves}手，"
                f"终局记分是{score}。"
            )

    else:
        raise ValueError(
            f"unsupported real game: {game}"
        )

    session_file = result.get("session_file")
    if not session_file or not Path(session_file).exists():
        raise RuntimeError(
            f"real game has no verified session file: {game}"
        )

    interest_event = {
        "excited": "great",
        "proud": "good",
        "happy": "good",
        "focused": "good",
        "mixed": "neutral",
        "annoyed": "bad",
        "frustrated": "frustrating",
        "confused": "mixed",
    }.get(mood, "neutral")

    await record_interest_event(
        kind="game",
        name=game,
        event=interest_event,
    )

    return {
        "mode": "real",
        "game": game,
        "mood": mood,
        "reaction": reaction,
        "result": result,
        "session_file": session_file,
        "verified": True,
    }


SIMULATED_GAMES = (
    "Minecraft",
    "崩坏：星穹铁道",
    "Muse Dash",
)

MEDIA_ACTIVITIES = (
    "刷视频",
    "随便翻翻视频",
    "窝着看一会儿视频",
)


def choose_entertainment_mode():
    """
    不使用每日硬额度。

    real:
        真正运行游戏引擎。

    simulated:
        虚拟生活中的模拟娱乐，
        数据库明确标记 simulated。

    media:
        普通刷视频/摸鱼行为。
        当前没有真实视频内容源时，
        不声称看过具体真实视频。
    """

    roll = random.random()

    if roll < 0.65:
        return "real"

    if roll < 0.88:
        return "simulated"

    return "media"


async def play_simulated_game(game=None):
    if game is None:
        game = await weighted_choice(
            "sim_game",
            SIMULATED_GAMES,
        )

    outcomes = [
        (
            "happy",
            f"模拟玩了会儿{game}，还挺上头的 (´▽｀)",
        ),
        (
            "relaxed",
            f"在自己的生活模拟里摸了会儿{game}，挺放松的。",
        ),
        (
            "focused",
            f"今天突然想玩{game}，结果认真折腾了好一阵。",
        ),
        (
            "annoyed",
            f"模拟玩{game}玩得有点不爽……哼 (｀へ´)",
        ),
    ]

    mood, reaction = random.choice(outcomes)

    return {
        "mode": "simulated",
        "game": game,
        "mood": mood,
        "reaction": reaction,
        "result": None,
        "session_file": None,
    }


def play_media():
    activity = random.choice(
        MEDIA_ACTIVITIES
    )

    reactions = [
        f"{activity}，脑子暂时放空一下。",
        f"{activity}，一不小心就摸鱼了 (￣▽￣)",
        f"{activity}，本来只想看一会儿的……",
        f"{activity}，今天就想懒一下。",
    ]

    return {
        "mode": "media",
        "game": "刷视频",
        "mood": random.choice(
            (
                "relaxed",
                "lazy",
                "amused",
                "calm",
            )
        ),
        "reaction": random.choice(
            reactions
        ),
        "result": None,
        "session_file": None,
    }


async def play_entertainment():
    mode = choose_entertainment_mode()

    if mode == "real":
        return await play_real_game()

    if mode == "simulated":
        result = await play_simulated_game()
        event = {
            "happy": "good",
            "focused": "good",
            "relaxed": "neutral",
            "annoyed": "bad",
        }.get(result.get("mood"), "neutral")
        await record_interest_event(
            kind="sim_game",
            name=result["game"],
            event=event,
        )
        return result

    return play_media()
