from __future__ import annotations
import json
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_PATH = Path("/opt/ying/data/telegram/mobile_event_log.jsonl")
BEIJING = timezone(timedelta(hours=8))


def record_event(kind: str, detail: str, *, game: str = "", result: dict | None = None, error: Exception | None = None):
    """以中文记录手机端与游戏事件；不记录密钥、会话令牌或私聊正文。"""
    item = {
        "时间": datetime.now(BEIJING).isoformat(timespec="seconds"),
        "类型": kind,
        "说明": detail,
        "游戏": game,
        "结果": result or {},
    }
    if error is not None:
        names = {"ValueError": "参数或记录错误", "TimeoutError": "运行超时", "FileNotFoundError": "文件不存在", "ConnectionError": "连接中断", "OSError": "系统文件或进程错误"}
        item["原因"] = names.get(type(error).__name__, "执行时发生异常")
        item["异常类型"] = type(error).__name__
        item["异常说明"] = str(error)[:600]
        item["调用位置"] = traceback.extract_tb(error.__traceback__)[-1].lineno if error.__traceback__ else 0
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    except OSError:
        # 记录故障不能阻断正常游戏和聊天。
        pass
    return item


def recent_events(limit: int = 80):
    if not LOG_PATH.exists():
        return []
    from collections import deque
    with LOG_PATH.open(encoding="utf-8") as file:
        lines = deque(file, maxlen=min(max(limit, 1), 200))
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    return rows
