
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_PATH = Path(
    "/opt/ying/data/telegram/life_log.jsonl"
)

TZ_CN = timezone(
    timedelta(hours=8)
)


def _now_iso():
    return datetime.now(
        TZ_CN
    ).isoformat(timespec="seconds")


def write_life_log(
    *,
    activity: str,
    event: str,
    mode: str = "normal",
    detail: str = "",
    mood: str = "",
    thought: str = "",
    source: str = "system",
):
    """
    写入一条生活日志。

    activity:
        chess / gomoku / jump_jump /
        match3 / pvz / resting / bored ...

    event:
        started / finished / idle /
        mood / note ...

    mode:
        real / simulated / media / normal
    """

    LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    item = {
        "time": _now_iso(),
        "activity": activity,
        "event": event,
        "mode": mode,
        "detail": detail,
        "mood": mood,
        "thought": thought,
        "source": source,
    }

    with LOG_PATH.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                item,
                ensure_ascii=False,
            )
            + "\n"
        )

    return item


def read_recent_life_log(
    limit: int = 20,
):
    if not LOG_PATH.exists():
        return []

    lines = LOG_PATH.read_text(
        encoding="utf-8"
    ).splitlines()

    result = []

    for line in lines[-limit:]:
        try:
            result.append(
                json.loads(line)
            )
        except Exception:
            continue

    return result


def read_today_life_log():
    today = datetime.now(
        TZ_CN
    ).date().isoformat()

    result = []

    for item in read_recent_life_log(
        limit=500
    ):
        time_text = str(
            item.get("time", "")
        )

        if time_text.startswith(today):
            result.append(item)

    return result


def format_life_log(
    items,
    *,
    detailed: bool = True,
):
    if not items:
        return "今天还没有生活记录。"

    lines = []

    for item in items:
        time_text = (
            item.get("time", "")
            [11:16]
        )

        detail = (
            item.get("detail")
            or item.get("event")
            or ""
        )

        lines.append(
            f"{time_text} {detail}"
        )

        if detailed:
            mood = (
                item.get("mood")
                or ""
            )

            thought = (
                item.get("thought")
                or ""
            )

            if mood:
                lines.append(
                    f"  心情：{mood}"
                )

            if thought:
                lines.append(
                    f"  碎碎念：{thought}"
                )

    return "\n".join(lines)
