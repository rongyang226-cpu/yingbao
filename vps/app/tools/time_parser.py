import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import dateparser

from app.config import YING_TIMEZONE
from app.tools.time_tool import local_now, local_zone


def _make_result(original: str, dt: datetime) -> dict:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_zone())
    else:
        dt = dt.astimezone(local_zone())

    utc_dt = dt.astimezone(timezone.utc)

    return {
        "original": original,
        "local": dt,
        "utc": utc_dt,
        "local_iso": dt.isoformat(),
        "utc_iso": utc_dt.isoformat(),
        "timezone": YING_TIMEZONE,
    }


def _parse_clock(text: str):
    """
    提取：
    3点
    3点30
    3点半
    15:30
    15：30
    """
    m = re.search(r"(\d{1,2})[:：](\d{1,2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.search(
        r"(\d{1,2})\s*点(?:\s*(\d{1,2})\s*分?)?(半)?",
        text,
    )

    if not m:
        return None

    hour = int(m.group(1))

    if m.group(3):
        minute = 30
    elif m.group(2):
        minute = int(m.group(2))
    else:
        minute = 0

    return hour, minute


def _apply_daypart(text: str, hour: int):
    if any(x in text for x in ("下午", "晚上", "傍晚")):
        if hour < 12:
            hour += 12

    elif "中午" in text:
        if 1 <= hour < 11:
            hour += 12

    elif "凌晨" in text:
        if hour == 12:
            hour = 0

    elif any(x in text for x in ("上午", "早上", "早晨")):
        if hour == 12:
            hour = 0

    return hour


def _relative(text: str, now: datetime):
    if "半小时后" in text:
        return now + timedelta(minutes=30)

    patterns = (
        (r"(\d+)\s*分钟后", "minutes"),
        (r"(\d+)\s*小时后", "hours"),
        (r"(\d+)\s*天后", "days"),
    )

    for pattern, unit in patterns:
        m = re.search(pattern, text)
        if not m:
            continue

        value = int(m.group(1))

        if unit == "minutes":
            return now + timedelta(minutes=value)
        if unit == "hours":
            return now + timedelta(hours=value)
        if unit == "days":
            return now + timedelta(days=value)

    return None



def _has_daypart(text: str) -> bool:
    return any(
        x in text
        for x in (
            "凌晨", "早上", "早晨", "上午",
            "中午", "下午", "傍晚", "晚上", "今晚",
        )
    )


def _explicit_chinese_time(text: str, now: datetime):
    """
    确定性处理常见中文时间。
    """

    # ----- 日期 -----

    if "后天" in text:
        target_date = (now + timedelta(days=2)).date()

    elif "明天" in text or "明日" in text:
        target_date = (now + timedelta(days=1)).date()

    elif "今天" in text or "今日" in text or "今晚" in text:
        target_date = now.date()

    else:
        # 9月25日 / 9月25号
        m = re.search(
            r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?",
            text,
        )

        if m:
            month = int(m.group(1))
            day = int(m.group(2))

            try:
                candidate = datetime(
                    now.year,
                    month,
                    day,
                    tzinfo=local_zone(),
                )

                # 已经过了则理解成下一年
                if candidate.date() < now.date():
                    candidate = candidate.replace(
                        year=now.year + 1
                    )

                target_date = candidate.date()

            except ValueError:
                return None
        else:
            target_date = None

    clock = _parse_clock(text)

    # “明天”这种只有日期没有钟点：
    # 先保留当前时刻，后续事件层可要求补充具体时间。
    if target_date is not None and clock is None:
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            now.hour,
            now.minute,
            now.second,
            tzinfo=local_zone(),
        )

    if clock is None:
        return None

    hour, minute = clock
    hour = _apply_daypart(text, hour)

    if hour > 23 or minute > 59:
        return None

    # 没说日期，只说“晚上8点”
    if target_date is None:
        target_date = now.date()

        candidate = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=local_zone(),
        )

        # 裸钟点没有“早上/下午/晚上”时，
        # 1~11 点同时考虑上午和下午，选择最近的未来时间。
        if not _has_daypart(text) and 1 <= hour <= 11:
            candidates = []

            for candidate_hour in (hour, hour + 12):
                c = datetime(
                    target_date.year,
                    target_date.month,
                    target_date.day,
                    candidate_hour,
                    minute,
                    tzinfo=local_zone(),
                )
                if c > now:
                    candidates.append(c)

            if candidates:
                nearest = min(candidates)
                hour = nearest.hour
            else:
                target_date = (
                    now + timedelta(days=1)
                ).date()

        # 明确时间段，或 12~23 点：过去则顺延一天
        elif candidate <= now:
            target_date = (
                now + timedelta(days=1)
            ).date()

    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=local_zone(),
    )


def parse_time(
    text: str,
    *,
    base_time: Optional[datetime] = None,
) -> Optional[dict]:

    if not text or not text.strip():
        return None

    original = text.strip()

    now = base_time or local_now()

    if now.tzinfo is None:
        now = now.replace(tzinfo=local_zone())
    else:
        now = now.astimezone(local_zone())

    # 1. 精确相对时间
    parsed = _relative(original, now)

    # 2. 我们自己的中文确定性解析
    if parsed is None:
        parsed = _explicit_chinese_time(
            original,
            now,
        )

    # 3. dateparser 仅兜底
    if parsed is None:
        parsed = dateparser.parse(
            original,
            languages=["zh"],
            settings={
                "RELATIVE_BASE": now.replace(
                    tzinfo=None
                ),
                "TIMEZONE": YING_TIMEZONE,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            },
        )

    if parsed is None:
        return None

    return _make_result(original, parsed)
