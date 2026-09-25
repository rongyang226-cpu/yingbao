from __future__ import annotations

import time
from pathlib import Path

import cairosvg
import chess
import chess.svg

RENDER_DIR = Path("/opt/ying/games/renders")
RENDER_DIR.mkdir(parents=True, exist_ok=True)


def render_board_png(
    board: chess.Board,
    *,
    lastmove: chess.Move | None = None,
    flipped: bool = False,
    size: int = 720,
    filename: str | None = None,
) -> str:
    if filename is None:
        filename = f"chess_{int(time.time())}.png"

    out = RENDER_DIR / filename

    svg = chess.svg.board(
        board=board,
        size=size,
        lastmove=lastmove,
        flipped=flipped,
        coordinates=True,
    )

    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(out),
    )

    return str(out)
