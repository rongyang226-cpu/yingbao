from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine

from games.visual.render_chess import render_board_png

ENGINE_PATH = "/usr/games/stockfish"
SESSION_DIR = Path("/opt/ying/games/duels")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _session_path(chat_id: int, user_id: int) -> Path:
    return SESSION_DIR / f"tg_chess_{chat_id}_{user_id}.json"


def has_active_session(chat_id: int, user_id: int) -> bool:
    return _session_path(chat_id, user_id).exists()


def load_session(chat_id: int, user_id: int):
    path = _session_path(chat_id, user_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(chat_id: int, user_id: int, data: dict):
    path = _session_path(chat_id, user_id)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def stop_session(
    chat_id: int,
    user_id: int,
    *,
    reason: str = "stopped",
) -> bool:
    """
    结束棋局时不删除，归档保存。
    """
    path = _session_path(
        chat_id,
        user_id,
    )

    if not path.exists():
        return False

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        data = {}

    data["status"] = "finished"
    data["ended_at"] = _now()
    data["end_reason"] = reason

    archive_dir = (
        SESSION_DIR / "archive"
    )

    archive_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    stamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    archive_path = archive_dir / (
        f"tg_chess_{chat_id}_{user_id}_{stamp}.json"
    )

    archive_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    path.unlink()

    return True


def get_recent_finished_games(
    chat_id: int,
    user_id: int,
    limit: int = 3,
):
    archive_dir = (
        SESSION_DIR / "archive"
    )

    if not archive_dir.exists():
        return []

    pattern = (
        f"tg_chess_{chat_id}_{user_id}_*.json"
    )

    files = sorted(
        archive_dir.glob(pattern),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )[:limit]

    result = []

    for path in files:
        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            continue

        moves = data.get("moves") or []

        result.append({
            "created_at": data.get("created_at"),
            "ended_at": data.get("ended_at"),
            "end_reason": data.get("end_reason"),
            "move_count": len(moves),
            "moves": moves[-12:],
            "fen": data.get("fen"),
            "archive_file": str(path),
        })

    return result



def restore_recent_stopped_session(
    chat_id: int,
    user_id: int,
):
    """
    恢复最近一盘由用户手动停止的棋局。
    已经自然结束/将死/和棋的棋局不恢复。
    """

    active_path = _session_path(
        chat_id,
        user_id,
    )

    if active_path.exists():
        return {
            "ok": True,
            "already_active": True,
        }

    archive_dir = SESSION_DIR / "archive"

    if not archive_dir.exists():
        return None

    pattern = (
        f"tg_chess_{chat_id}_{user_id}_*.json"
    )

    files = sorted(
        archive_dir.glob(pattern),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

    for archive_path in files:
        try:
            data = json.loads(
                archive_path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            continue

        # 只恢复手动停止的棋局
        if data.get("end_reason") != "stopped":
            continue

        fen = data.get("fen")

        if not fen:
            continue

        try:
            board = chess.Board(fen)
        except Exception:
            continue

        # 已经真正结束的局不能恢复
        if board.is_game_over():
            continue

        data["status"] = "active"
        data["updated_at"] = _now()

        data.pop("ended_at", None)
        data.pop("end_reason", None)

        # 老归档如果没有候选走法，重新生成
        if not data.get("choices"):
            data["choices"] = _beginner_choices(
                board,
                limit=5,
            )

        save_session(
            chat_id,
            user_id,
            data,
        )

        archive_path.unlink()

        return {
            "ok": True,
            "already_active": False,
            "fen": board.fen(),
        }

    return None



def _result_text(result: str) -> str:
    if result == "1-0":
        return "白方胜"
    if result == "0-1":
        return "黑方胜"
    if result == "1/2-1/2":
        return "和棋"
    return result


def _playful_turn_comment(
    board: chess.Board,
    user_san: str,
    engine_san: str,
    *,
    user_capture: bool = False,
    engine_capture: bool = False,
):
    parts = []

    # 用户这一步
    if user_capture:
        parts.append(
            random.choice([
                f"哎？{user_san}……你还真敢吃啊。",
                f"{user_san}？行嘛，开始凶起来了。",
                f"好好好，{user_san}，还真让你捞到一个 (￣▽￣)",
                f"居然直接 {user_san}……我记住了。",
            ])
        )
    else:
        parts.append(
            random.choice([
                f"{user_san}啊……嗯，我看看。",
                f"哦？你选了 {user_san}。",
                f"{user_san}？这个想法倒还行。",
                f"嗯……{user_san}，先这么走是吧。",
                f"行，{user_san}，让我想想怎么欺负你。",
            ])
        )

    # 萤自己的回应
    if engine_capture:
        parts.append(
            random.choice([
                f"那这个我就收下啦，{engine_san}。",
                f"嘿嘿，{engine_san}，这颗我可拿走了。",
                f"那我不客气咯——{engine_san}。",
                f"{engine_san}。嗯，这个便宜我得占 (￣▽￣)",
            ])
        )

    elif board.is_check():
        parts.append(
            random.choice([
                f"那我走 {engine_san}。将军～",
                f"{engine_san}。小心点，我开始凶了。",
                f"我选 {engine_san}。嗯哼，将军。",
            ])
        )

    else:
        parts.append(
            random.choice([
                f"那我就走 {engine_san}。",
                f"我想一下……{engine_san}。",
                f"行，那我接 {engine_san}。",
                f"那我这里走 {engine_san} 好了。",
                f"轮到我嘛……那就 {engine_san}。",
            ])
        )

    # 不每回合都重复“不会下就回数字”
    # 只偶尔补一句，让聊天没那么像教程。
    if random.random() < 0.55:
        parts.append(
            random.choice([
                "到你啦。",
                "来，看看你这次选哪个。",
                "你慢慢想，我又不催你。",
                "嗯哼，接下来怎么办？",
                "要是拿不准就问我，我可以给你出主意。",
                "别急着乱点啊，先看看棋盘。",
                "这回我倒想看看你准备怎么走。",
            ])
        )

    return "\n".join(parts)



def _reaction_after_engine(board: chess.Board, san: str) -> str:
    if board.is_checkmate():
        return random.choice([
            f"我走 {san}。将死啦……这盘结束。",
            f"{san}。唔，直接收掉了。",
        ])

    if board.is_check():
        return random.choice([
            f"我走 {san}。将军 (￣▽￣)",
            f"{san}。先给你一点压力。",
        ])

    return random.choice([
        f"我走 {san}。",
        f"轮到我啦，我走 {san}。",
        f"{san}。继续。",
        f"我下 {san}，慢慢来。",
    ])


def _reaction_on_finish(result: str) -> str:
    if result == "1-0":
        return "这局你赢了……哼，下盘再来。"
    if result == "0-1":
        return "这局我拿下啦 (￣︶￣)"
    if result == "1/2-1/2":
        return "和棋……这盘缠得还挺久。"
    return "这盘结束了。"


def _parse_user_move(
    board: chess.Board,
    text: str,
    choices=None,
):
    raw = str(text or "").strip()

    if not raw:
        return None

    low = raw.lower()

    # 只有明确结束词才结束棋局。
    if low in {
        "stop",
        "quit",
        "resign",
        "投降",
        "认输",
        "不下了",
        "结束",
    }:
        return "resign"

    # 新手数字选择：
    # 5
    # 5!
    # emm5!
    # 我选5
    # 第5个
    # 那就5吧
    if choices:
        matches = re.findall(
            r"(?<!\d)([1-9])(?!\d)",
            raw,
        )

        for value in matches:
            index = int(value) - 1

            if not (
                0 <= index < len(choices)
            ):
                continue

            try:
                move = chess.Move.from_uci(
                    choices[index]["uci"]
                )

                if move in board.legal_moves:
                    return move

            except Exception:
                continue

    # 标准 SAN，例如 e4 / Nf3 / O-O
    try:
        return board.parse_san(raw)
    except Exception:
        pass

    # UCI，例如 e2e4
    try:
        mv = chess.Move.from_uci(low)

        if mv in board.legal_moves:
            return mv

    except Exception:
        pass

    # 没有合法棋步：
    # 返回 None，让 Telegram 正常聊天系统接管。
    return None


def _beginner_choices(board: chess.Board, limit: int = 5):
    """
    给新手生成少量合法走法。
    优先由 Stockfish 给出较合理的候选，
    用户只需要回复数字。
    """
    choices = []

    try:
        with chess.engine.SimpleEngine.popen_uci(
            ENGINE_PATH
        ) as engine:
            infos = engine.analyse(
                board,
                chess.engine.Limit(depth=6),
                multipv=min(
                    limit,
                    len(list(board.legal_moves)),
                ),
            )

        if isinstance(infos, dict):
            infos = [infos]

        for info in infos:
            pv = info.get("pv") or []

            if not pv:
                continue

            move = pv[0]

            if move not in board.legal_moves:
                continue

            san = board.san(move)

            if not any(
                item["uci"] == move.uci()
                for item in choices
            ):
                choices.append({
                    "uci": move.uci(),
                    "san": san,
                })

    except Exception:
        pass

    # 引擎候选不够时用合法走法补齐。
    if len(choices) < limit:
        for move in board.legal_moves:
            if any(
                item["uci"] == move.uci()
                for item in choices
            ):
                continue

            choices.append({
                "uci": move.uci(),
                "san": board.san(move),
            })

            if len(choices) >= limit:
                break

    return choices


def _choices_text(choices):
    if not choices:
        return ""

    lines = [
        "",
        "不会下也没关系，直接回数字：",
    ]

    for i, item in enumerate(
        choices,
        start=1,
    ):
        lines.append(
            f"{i}. {item['san']}"
        )

    return "\n".join(lines)


def _engine_best_move(board: chess.Board, depth: int = 8) -> chess.Move:
    with chess.engine.SimpleEngine.popen_uci(ENGINE_PATH) as engine:
        result = engine.play(
            board,
            chess.engine.Limit(depth=depth),
        )
        return result.move


async def start_duel(chat_id: int, user_id: int, user_name: str):
    board = chess.Board()
    data = {
        "chat_id": chat_id,
        "user_id": user_id,
        "user_name": user_name,
        "user_color": "white",
        "engine_color": "black",
        "fen": board.fen(),
        "moves": [],
        "depth": 8,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "active",
    }
    data["choices"] = _beginner_choices(
        board,
        limit=5,
    )

    save_session(chat_id, user_id, data)

    image_path = render_board_png(
        board,
        filename=f"chess_start_{chat_id}_{user_id}.png",
        flipped=False,
    )

    caption = (
        "国际象棋开始啦。\n"
        "你执白，我执黑。\n"
        "不会下也没关系，直接回下面的数字就行。\n"
        "也可以自己发 e4 / Nf3 / O-O。\n"
        "结束对局用：/chess_stop"
        + _choices_text(data["choices"])
    )

    return {
        "ok": True,
        "image_path": image_path,
        "caption": caption,
    }


async def play_user_move(chat_id: int, user_id: int, text: str):
    data = load_session(chat_id, user_id)
    if not data:
        return {
            "handled": False,
        }

    board = chess.Board(data["fen"])
    choices = data.get("choices") or []
    parsed = _parse_user_move(
        board,
        text,
        choices,
    )

    if parsed == "resign":
        stop_session(chat_id, user_id, reason="resign")
        return {
            "handled": True,
            "ok": False,
            "reply": "好吧，这盘先记你认输……下次再来。"
        }

    if parsed is None:
        # 不像棋步的普通文字交回正常聊天系统处理。
        # 棋局 session 保持不变，不退出、不丢盘面。
        return {
            "handled": False,
            "ok": False,
        }

    user_san = board.san(parsed)
    user_capture = board.is_capture(parsed)
    board.push(parsed)
    data["moves"].append({
        "side": "user",
        "move": user_san,
        "at": _now(),
    })

    # 用户走完直接结束
    if board.is_game_over():
        result = board.result()
        image_path = render_board_png(
            board,
            lastmove=parsed,
            filename=f"chess_end_{chat_id}_{user_id}.png",
            flipped=False,
        )
        stop_session(chat_id, user_id, reason="finished")

        caption = (
            f"你走 {user_san}。\n"
            f"对局结束：{_result_text(result)}\n"
            f"{_reaction_on_finish(result)}"
        )

        return {
            "handled": True,
            "ok": True,
            "image_path": image_path,
            "caption": caption,
        }

    engine_move = await asyncio.to_thread(
        _engine_best_move,
        board,
        data.get("depth", 8),
    )

    engine_san = board.san(engine_move)
    engine_capture = board.is_capture(engine_move)
    board.push(engine_move)

    data["moves"].append({
        "side": "ying",
        "move": engine_san,
        "at": _now(),
    })
    data["fen"] = board.fen()
    data["updated_at"] = _now()

    data["choices"] = _beginner_choices(
        board,
        limit=5,
    )

    image_path = render_board_png(
        board,
        lastmove=engine_move,
        filename=f"chess_turn_{chat_id}_{user_id}.png",
        flipped=False,
    )

    if board.is_game_over():
        result = board.result()
        stop_session(chat_id, user_id)
        caption = (
            f"你走 {user_san}。\n"
            f"{_reaction_after_engine(board, engine_san)}\n"
            f"对局结束：{_result_text(result)}\n"
            f"{_reaction_on_finish(result)}"
        )
        return {
            "handled": True,
            "ok": True,
            "image_path": image_path,
            "caption": caption,
        }

    save_session(chat_id, user_id, data)

    caption = (
        _playful_turn_comment(
            board,
            user_san,
            engine_san,
            user_capture=user_capture,
            engine_capture=engine_capture,
        )
        + _choices_text(
            data.get("choices") or []
        )
    )

    return {
        "handled": True,
        "ok": True,
        "image_path": image_path,
        "caption": caption,
    }


async def get_status(chat_id: int, user_id: int):
    data = load_session(chat_id, user_id)
    if not data:
        return None

    board = chess.Board(data["fen"])
    moves = data.get("moves", [])
    last = moves[-1]["move"] if moves else "无"

    return {
        "status": data.get("status", "active"),
        "fen": board.fen(),
        "fullmove": board.fullmove_number,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "last_move": last,
    }


async def get_status_view(chat_id: int, user_id: int):
    data = load_session(chat_id, user_id)
    if not data:
        return None

    board = chess.Board(data["fen"])
    moves = data.get("moves", [])
    choices = data.get("choices") or []

    last = moves[-1]["move"] if moves else "无"

    image_path = render_board_png(
        board,
        filename=f"chess_status_{chat_id}_{user_id}.png",
        flipped=False,
    )

    caption = (
        "喏，棋盘还在这儿。\n"
        f"现在轮到：{'你（白方）' if board.turn == chess.WHITE else '我（黑方）'}\n"
        f"当前回合：{board.fullmove_number}\n"
        f"上一手：{last}\n"
        "你不会下也没关系，直接回数字就行。"
        + _choices_text(choices)
    )

    return {
        "status": data.get("status", "active"),
        "fen": board.fen(),
        "fullmove": board.fullmove_number,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "last_move": last,
        "image_path": image_path,
        "caption": caption,
    }


async def get_chat_context(chat_id: int, user_id: int):
    """
    给普通聊天模型看的当前棋局上下文。
    只提供真实棋盘和候选走法，不自动替用户落子。
    """
    data = load_session(chat_id, user_id)

    if not data:
        return ""

    board = chess.Board(data["fen"])
    choices = data.get("choices") or []
    moves = data.get("moves") or []

    lines = [
        "【当前正在进行的国际象棋陪玩】",
        "- 棋局仍在进行中。",
        "- 用户执白，萤执黑。",
        f"- 当前回合: {board.fullmove_number}",
        f"- 当前轮到: {'用户（白方）' if board.turn == chess.WHITE else '萤（黑方）'}",
        f"- FEN: {board.fen()}",
    ]

    if moves:
        recent = moves[-6:]
        move_text = " / ".join(
            f"{x.get('side')}:{x.get('move')}"
            for x in recent
        )
        lines.append(
            f"- 最近走法: {move_text}"
        )

    if choices:
        lines.append("- 用户当前可直接选择的推荐走法：")

        for i, item in enumerate(
            choices,
            start=1,
        ):
            lines.append(
                f"  {i}. {item['san']} ({item['uci']})"
            )

    lines += [
        "- 如果用户问“哪个好”“选哪个”“怎么走”等，默认是在问上面的当前棋局。",
        "- 可以自然推荐某个编号并简单解释原因。",
        "- 不要声称用户已经走了某一步，除非棋局记录里确实已经执行。",
        "- 用户只是询问意见时，不要自行替用户落子。",
        "- 用户真正发送有效编号/棋步后，才由棋局程序执行。",
    ]

    return "\n".join(lines)


async def get_recent_game_memory(
    chat_id: int,
    user_id: int,
    limit: int = 2,
):
    games = get_recent_finished_games(
        chat_id,
        user_id,
        limit=limit,
    )

    if not games:
        return ""

    lines = [
        "【最近结束的国际象棋对局】",
    ]

    for index, game in enumerate(
        games,
        start=1,
    ):
        lines.append(
            f"- 第{index}盘："
            f"结束原因={game.get('end_reason') or '未知'}，"
            f"共记录{game.get('move_count') or 0}个半回合。"
        )

        moves = game.get("moves") or []

        if moves:
            move_text = " / ".join(
                f"{x.get('side')}:{x.get('move')}"
                for x in moves
            )

            lines.append(
                f"  最近走法：{move_text}"
            )

    lines += [
        "- 这些是真实归档的历史棋局，可以自然回忆。",
        "- 如果用户问“刚才那盘”“刚才下得怎么样”等，优先参考最近一盘。",
        "- 不要把未发生的走法或胜负编进去。",
    ]

    return "\n".join(lines)
