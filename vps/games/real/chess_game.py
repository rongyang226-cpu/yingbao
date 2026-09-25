
import json
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine

ENGINE = "/usr/games/stockfish"
SESSION_DIR = Path("/opt/ying/games/sessions")


def now():
    return datetime.now(timezone.utc).isoformat()


def play_game(max_plies=300, depth=4):
    board = chess.Board()
    moves = []
    started_at = now()

    white = chess.engine.SimpleEngine.popen_uci(ENGINE)
    black = chess.engine.SimpleEngine.popen_uci(ENGINE)

    try:
        for ply in range(max_plies):
            if board.is_game_over(claim_draw=True):
                break

            engine = white if board.turn else black

            result = engine.play(
                board,
                chess.engine.Limit(depth=depth)
            )

            move = result.move
            san = board.san(move)

            moves.append({
                "ply": ply + 1,
                "side": "white" if board.turn else "black",
                "uci": move.uci(),
                "san": san,
            })

            board.push(move)

        data = {
            "game": "chess",
            "mode": "real",
            "started_at": started_at,
            "ended_at": now(),
            "result": board.result(claim_draw=True),
            "move_count": len(moves),
            "moves": moves,
            "final_fen": board.fen(),
        }

        SESSION_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        filename = (
            "chess_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + ".json"
        )

        path = SESSION_DIR / filename

        path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        data["session_file"] = str(path)
        return data

    finally:
        white.quit()
        black.quit()
