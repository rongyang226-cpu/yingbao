from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import YING_TIMEZONE


def local_zone():
    return ZoneInfo(YING_TIMEZONE)


def utc_now():
    """数据库、内部状态统一使用 UTC。"""
    return datetime.now(timezone.utc)


def local_now():
    """萤当前所处的本地时间。"""
    return utc_now().astimezone(local_zone())


def utc_iso():
    return utc_now().isoformat()


def local_iso():
    return local_now().isoformat()


def build_time_context():
    """
    提供给模型的真实当前时间。
    相对时间的最终解析以后仍由程序完成，
    不能仅依赖模型猜测。
    """
    dt = local_now()

    weekdays = (
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
        "星期日",
    )

    return "\n".join([
        f"timezone={YING_TIMEZONE}",
        f"local_date={dt:%Y-%m-%d}",
        f"local_time={dt:%H:%M:%S}",
        f"weekday={weekdays[dt.weekday()]}",
        f"utc_time={utc_now().isoformat()}",
    ])
