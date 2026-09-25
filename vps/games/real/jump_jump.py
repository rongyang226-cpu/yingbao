
import json
import random
from datetime import datetime, timezone
from pathlib import Path

SESSION_DIR = Path("/opt/ying/games/sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def choose_charge(distance):
    """
    一个简单自动玩家：
    根据距离估算蓄力，并带一点随机误差。
    """
    base = distance / 2.6
    noise = random.uniform(-0.18, 0.18)
    return clamp(base * (1.0 + noise), 0.12, 1.50)


def jump_distance_from_charge(charge):
    """
    蓄力 -> 跳跃距离
    """
    return charge * 2.6


def play_one_game():
    score = 0
    combo = 0
    rounds = []

    step = 0
    while True:
        step += 1
        target_distance = random.uniform(0.8, 3.6)
        platform_radius = random.uniform(0.22, 0.45)

        charge = choose_charge(target_distance)
        actual_distance = jump_distance_from_charge(charge)

        error = actual_distance - target_distance

        landed = abs(error) <= platform_radius

        if landed:
            combo += 1

            center_bonus = abs(error) <= platform_radius * 0.25

            gain = 1

            if center_bonus:
                gain += min(combo // 3, 5)

            score += gain
        else:
            combo = 0

        rounds.append({
            "round": step,
            "target_distance": round(target_distance, 3),
            "platform_radius": round(platform_radius, 3),
            "charge": round(charge, 3),
            "actual_distance": round(actual_distance, 3),
            "error": round(error, 3),
            "landed": landed,
            "score_after": score,
        })

        if not landed:
            break

    result = {
        "game": "jump_jump",
        "mode": "real",
        "score": score,
        "rounds": len(rounds),
        "success_jumps": sum(
            1 for x in rounds if x["landed"]
        ),
        "failed": bool(rounds and not rounds[-1]["landed"]),
        "history": rounds,
        "finished_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    path = SESSION_DIR / f"jump_jump_{stamp}.json"

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
            "rounds": result["rounds"],
            "success_jumps": result["success_jumps"],
            "failed": result["failed"],
            "session": str(path),
        },
        ensure_ascii=False,
        indent=2,
    ))

    return result


def play_game():
    return play_one_game()


if __name__ == "__main__":
    play_one_game()
