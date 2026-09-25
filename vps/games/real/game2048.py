
import json
import random
from datetime import datetime, timezone
from pathlib import Path

SESSION_DIR = Path("/opt/ying/games/sessions")


def now():
    return datetime.now(timezone.utc).isoformat()


class Game2048:
    def __init__(self):
        self.board = [[0] * 4 for _ in range(4)]
        self.score = 0
        self.spawn()
        self.spawn()

    def spawn(self):
        empty = [
            (r, c)
            for r in range(4)
            for c in range(4)
            if self.board[r][c] == 0
        ]

        if not empty:
            return False

        r, c = random.choice(empty)
        self.board[r][c] = 4 if random.random() < 0.10 else 2
        return True

    def merge_line(self, line):
        vals = [x for x in line if x]
        out = []
        gain = 0
        i = 0

        while i < len(vals):
            if i + 1 < len(vals) and vals[i] == vals[i + 1]:
                v = vals[i] * 2
                out.append(v)
                gain += v
                i += 2
            else:
                out.append(vals[i])
                i += 1

        out += [0] * (4 - len(out))
        return out, gain

    def rotate(self):
        self.board = [
            list(row)
            for row in zip(*self.board[::-1])
        ]

    def move_left(self):
        changed = False
        gain = 0
        new_board = []

        for row in self.board:
            new_row, g = self.merge_line(row)

            if new_row != row:
                changed = True

            gain += g
            new_board.append(new_row)

        if changed:
            self.board = new_board
            self.score += gain

        return changed

    def move(self, direction):
        turns = {
            "left": 0,
            "down": 1,
            "right": 2,
            "up": 3,
        }[direction]

        for _ in range(turns):
            self.rotate()

        changed = self.move_left()

        for _ in range((4 - turns) % 4):
            self.rotate()

        if changed:
            self.spawn()

        return changed

    def can_move(self):
        for r in range(4):
            for c in range(4):
                if self.board[r][c] == 0:
                    return True

                if r < 3 and self.board[r][c] == self.board[r + 1][c]:
                    return True

                if c < 3 and self.board[r][c] == self.board[r][c + 1]:
                    return True

        return False

    def max_tile(self):
        return max(max(row) for row in self.board)


def evaluate_board(board, score):
    empty = sum(
        1
        for row in board
        for x in row
        if x == 0
    )

    maximum = max(
        max(row)
        for row in board
    )

    # 尽量让大数字待在角落。
    corners = (
        board[0][0],
        board[0][3],
        board[3][0],
        board[3][3],
    )

    corner_bonus = (
        maximum * 8
        if maximum in corners
        else 0
    )

    # 相邻相同数字意味着后面还有合并空间。
    merge_bonus = 0

    for r in range(4):
        for c in range(4):
            v = board[r][c]

            if not v:
                continue

            if r < 3 and board[r + 1][c] == v:
                merge_bonus += v * 2

            if c < 3 and board[r][c + 1] == v:
                merge_bonus += v * 2

    # 平滑度：相邻数字差距不要太离谱。
    roughness = 0

    for r in range(4):
        for c in range(4):
            v = board[r][c]

            if not v:
                continue

            if r < 3 and board[r + 1][c]:
                roughness += abs(
                    v - board[r + 1][c]
                )

            if c < 3 and board[r][c + 1]:
                roughness += abs(
                    v - board[r][c + 1]
                )

    return (
        empty * 1000
        + corner_bonus
        + merge_bonus * 4
        + score * 0.15
        - roughness * 0.12
    )


def choose_move(game):
    candidates = []

    # 稍微偏向下/左，让大块更容易稳定在角落。
    preference = {
        "down": 3.0,
        "left": 2.0,
        "right": 0.5,
        "up": 0.0,
    }

    for direction in (
        "down",
        "left",
        "right",
        "up",
    ):
        test = Game2048.__new__(Game2048)

        test.board = [
            row[:]
            for row in game.board
        ]

        test.score = game.score

        # 候选评估时暂时禁止随机生成新块，
        # 否则每次评分都会被随机数干扰。
        original_spawn = test.spawn
        test.spawn = lambda: True

        changed = test.move(direction)

        test.spawn = original_spawn

        if not changed:
            continue

        value = evaluate_board(
            test.board,
            test.score,
        )

        value += preference[direction]

        # 只留一点点随机性，
        # 避免每一局完全一模一样。
        value += random.random() * 2

        candidates.append(
            (value, direction)
        )

    if not candidates:
        return None

    candidates.sort(reverse=True)

    return candidates[0][1]


def play_game(max_moves=1200):
    game = Game2048()
    moves = []
    started_at = now()

    for turn in range(max_moves):
        if not game.can_move():
            break

        direction = choose_move(game)

        if direction is None:
            break

        if not game.move(direction):
            continue

        moves.append({
            "turn": turn + 1,
            "direction": direction,
            "score": game.score,
            "max_tile": game.max_tile(),
            "board": [row[:] for row in game.board],
        })

        if game.max_tile() >= 2048:
            break

    data = {
        "game": "2048",
        "mode": "real",
        "started_at": started_at,
        "ended_at": now(),
        "score": game.score,
        "max_tile": game.max_tile(),
        "move_count": len(moves),
        "won": game.max_tile() >= 2048,
        "final_board": game.board,
        "moves": moves,
    }

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    filename = (
        "2048_"
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
