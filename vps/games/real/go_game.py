from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

GNUGO = "/usr/games/gnugo"
SESSIONS = Path("/opt/ying/games/sessions")
SESSIONS.mkdir(parents=True, exist_ok=True)


def _gtp_command(proc, command: str) -> str:
    proc.stdin.write(command + "\n")
    proc.stdin.flush()

    lines = []
    while True:
        line = proc.stdout.readline()
        if line == "":
            raise RuntimeError("GNU Go closed unexpectedly")

        stripped = line.rstrip("\n")
        if stripped == "":
            break

        lines.append(stripped)

    if not lines:
        return ""

    first = lines[0]
    if first.startswith("?"):
        raise RuntimeError(
            f"GNU Go command failed: {command}: "
            + " ".join(lines)
        )

    if first.startswith("="):
        lines[0] = first[1:].strip()

    return "\n".join(x for x in lines if x).strip()


def play_game(
    board_size: int = 9,
    max_moves: int = 180,
):
    """
    GNU Go 真实引擎自对弈。
    9x9 让 VPS 运行很轻，结果与每手都实际由 GNU Go 生成。
    """
    board_size = int(board_size)
    if board_size not in (9, 13, 19):
        board_size = 9

    proc = subprocess.Popen(
        [
            GNUGO,
            "--mode",
            "gtp",
            "--quiet",
            "--level",
            "5",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    moves = []
    passes = 0

    try:
        _gtp_command(proc, f"boardsize {board_size}")
        _gtp_command(proc, "clear_board")
        _gtp_command(proc, "komi 6.5")

        color = "black"

        for _ in range(max_moves):
            move = _gtp_command(
                proc,
                f"genmove {color}",
            ).strip()

            moves.append({
                "color": color,
                "move": move,
            })

            if move.lower() == "pass":
                passes += 1
            else:
                passes = 0

            if passes >= 2:
                break

            color = (
                "white"
                if color == "black"
                else "black"
            )

        final_score = _gtp_command(
            proc,
            "final_score",
        ).strip()

        try:
            sgf = _gtp_command(
                proc,
                "printsgf -",
            )
        except Exception:
            sgf = ""

    finally:
        try:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
        except Exception:
            pass

        try:
            proc.wait(timeout=4)
        except Exception:
            proc.kill()

    if final_score.startswith("B+"):
        winner = "black"
    elif final_score.startswith("W+"):
        winner = "white"
    elif final_score in ("0", "Draw", "draw"):
        winner = "draw"
    else:
        winner = "unknown"

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    session_path = (
        SESSIONS
        / f"go_{stamp}.json"
    )

    data = {
        "game": "go",
        "engine": "GNU Go 3.8",
        "board_size": board_size,
        "move_count": len(moves),
        "winner": winner,
        "final_score": final_score,
        "moves": moves,
        "sgf": sgf,
        "session_file": str(session_path),
    }

    session_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return data


if __name__ == "__main__":
    print(
        json.dumps(
            play_game(),
            ensure_ascii=False,
            indent=2,
        )
    )
