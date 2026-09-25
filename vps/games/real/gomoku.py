
import json
import random
from datetime import datetime, timezone
from pathlib import Path

SIZE = 15
EMPTY = 0
BLACK = 1
WHITE = 2

SESSION_DIR = Path("/opt/ying/games/sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


class Gomoku:
    def __init__(self):
        self.board = [
            [EMPTY for _ in range(SIZE)]
            for _ in range(SIZE)
        ]
        self.moves = []

    def legal(self, row, col):
        return (
            0 <= row < SIZE
            and 0 <= col < SIZE
            and self.board[row][col] == EMPTY
        )

    def place(self, row, col, player):
        if not self.legal(row, col):
            return False

        self.board[row][col] = player
        self.moves.append({
            "player": player,
            "row": row,
            "col": col,
        })
        return True

    def win(self, row, col, player):
        directions = [
            (1, 0),
            (0, 1),
            (1, 1),
            (1, -1),
        ]

        for dr, dc in directions:
            count = 1

            for sign in (-1, 1):
                r = row + dr * sign
                c = col + dc * sign

                while (
                    0 <= r < SIZE
                    and 0 <= c < SIZE
                    and self.board[r][c] == player
                ):
                    count += 1
                    r += dr * sign
                    c += dc * sign

            if count >= 5:
                return True

        return False

    def available(self):
        return [
            (r, c)
            for r in range(SIZE)
            for c in range(SIZE)
            if self.board[r][c] == EMPTY
        ]


def choose_move(game, player):
    opponent = WHITE if player == BLACK else BLACK

    # 先尝试直接获胜
    for r, c in game.available():
        game.board[r][c] = player
        won = game.win(r, c, player)
        game.board[r][c] = EMPTY

        if won:
            return r, c

    # 再尝试堵住对方五连
    for r, c in game.available():
        game.board[r][c] = opponent
        danger = game.win(r, c, opponent)
        game.board[r][c] = EMPTY

        if danger:
            return r, c

    # 优先靠近已有棋子
    candidates = []

    for r, c in game.available():
        nearby = 0

        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue

                rr = r + dr
                cc = c + dc

                if (
                    0 <= rr < SIZE
                    and 0 <= cc < SIZE
                    and game.board[rr][cc] != EMPTY
                ):
                    nearby += 1

        if nearby:
            candidates.append(
                (nearby, random.random(), r, c)
            )

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][2], candidates[0][3]

    return SIZE // 2, SIZE // 2


def run_demo():
    game = Gomoku()
    player = BLACK
    winner = None

    for _ in range(SIZE * SIZE):
        move = choose_move(game, player)

        if not move:
            break

        row, col = move
        game.place(row, col, player)

        if game.win(row, col, player):
            winner = player
            break

        player = WHITE if player == BLACK else BLACK

    result = {
        "game": "gomoku",
        "mode": "real",
        "winner": (
            "black"
            if winner == BLACK
            else "white"
            if winner == WHITE
            else "draw"
        ),
        "move_count": len(game.moves),
        "moves": game.moves,
        "finished_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S")

    path = SESSION_DIR / f"gomoku_{stamp}.json"

    result["session_file"] = str(path)

    path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "winner": result["winner"],
            "move_count": result["move_count"],
            "session": str(path),
        },
        ensure_ascii=False,
        indent=2,
    ))

    return result


def play_game():
    return run_demo()


if __name__ == "__main__":
    run_demo()
