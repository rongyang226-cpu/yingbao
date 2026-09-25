
import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROWS = 8
COLS = 8
KINDS = 6

SESSION_DIR = Path("/opt/ying/games/sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


class Match3:
    def __init__(self):
        self.board = self._new_board()
        self.score = 0
        self.moves = []
        self.combo_count = 0

    def _new_board(self):
        while True:
            board = [
                [random.randrange(KINDS) for _ in range(COLS)]
                for _ in range(ROWS)
            ]
            self._remove_initial_matches(board)
            if self.find_valid_moves(board):
                return board

    def _remove_initial_matches(self, board):
        changed = True

        while changed:
            changed = False
            matches = self.find_matches(board)

            if not matches:
                break

            changed = True

            for r, c in matches:
                board[r][c] = random.randrange(KINDS)

    def find_matches(self, board=None):
        if board is None:
            board = self.board

        matched = set()

        # 横向
        for r in range(ROWS):
            c = 0
            while c < COLS:
                start = c
                value = board[r][c]

                while (
                    c + 1 < COLS
                    and board[r][c + 1] == value
                ):
                    c += 1

                if c - start + 1 >= 3:
                    for x in range(start, c + 1):
                        matched.add((r, x))

                c += 1

        # 纵向
        for c in range(COLS):
            r = 0
            while r < ROWS:
                start = r
                value = board[r][c]

                while (
                    r + 1 < ROWS
                    and board[r + 1][c] == value
                ):
                    r += 1

                if r - start + 1 >= 3:
                    for x in range(start, r + 1):
                        matched.add((x, c))

                r += 1

        return matched

    def swap(self, a, b):
        (r1, c1), (r2, c2) = a, b
        self.board[r1][c1], self.board[r2][c2] = (
            self.board[r2][c2],
            self.board[r1][c1],
        )

    def valid_swap(self, a, b, board=None):
        if board is None:
            board = self.board

        (r1, c1), (r2, c2) = a, b

        if abs(r1 - r2) + abs(c1 - c2) != 1:
            return False

        board[r1][c1], board[r2][c2] = (
            board[r2][c2],
            board[r1][c1],
        )

        ok = bool(self.find_matches(board))

        board[r1][c1], board[r2][c2] = (
            board[r2][c2],
            board[r1][c1],
        )

        return ok

    def find_valid_moves(self, board=None):
        if board is None:
            board = self.board

        result = []

        for r in range(ROWS):
            for c in range(COLS):
                if c + 1 < COLS:
                    a = (r, c)
                    b = (r, c + 1)

                    if self.valid_swap(a, b, board):
                        result.append((a, b))

                if r + 1 < ROWS:
                    a = (r, c)
                    b = (r + 1, c)

                    if self.valid_swap(a, b, board):
                        result.append((a, b))

        return result

    def collapse_and_fill(self):
        for c in range(COLS):
            values = [
                self.board[r][c]
                for r in range(ROWS)
                if self.board[r][c] is not None
            ]

            missing = ROWS - len(values)

            new_values = [
                random.randrange(KINDS)
                for _ in range(missing)
            ] + values

            for r in range(ROWS):
                self.board[r][c] = new_values[r]

    def resolve(self):
        chain = 0
        total_removed = 0

        while True:
            matches = self.find_matches()

            if not matches:
                break

            chain += 1
            removed = len(matches)
            total_removed += removed

            gain = removed * 10 * chain
            self.score += gain

            for r, c in matches:
                self.board[r][c] = None

            self.collapse_and_fill()

        return {
            "chains": chain,
            "removed": total_removed,
        }

    def shuffle(self):
        flat = [
            self.board[r][c]
            for r in range(ROWS)
            for c in range(COLS)
        ]

        for _ in range(100):
            random.shuffle(flat)

            for r in range(ROWS):
                for c in range(COLS):
                    self.board[r][c] = flat[
                        r * COLS + c
                    ]

            if (
                not self.find_matches()
                and self.find_valid_moves()
            ):
                return True

        self.board = self._new_board()
        return True

    def play_auto(self, max_moves=80):
        for turn in range(1, max_moves + 1):
            valid = self.find_valid_moves()

            if not valid:
                self.shuffle()
                valid = self.find_valid_moves()

            if not valid:
                break

            a, b = random.choice(valid)

            before = self.score

            self.swap(a, b)
            result = self.resolve()

            self.moves.append({
                "turn": turn,
                "from": a,
                "to": b,
                "score_gain": self.score - before,
                "chains": result["chains"],
                "removed": result["removed"],
            })

        return {
            "game": "match3",
            "mode": "real",
            "score": self.score,
            "move_count": len(self.moves),
            "moves": self.moves,
            "finished_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }


def run_demo():
    game = Match3()
    result = game.play_auto()

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    path = SESSION_DIR / f"match3_{stamp}.json"

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
            "score": result["score"],
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
