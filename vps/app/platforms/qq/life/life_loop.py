import asyncio
import logging
import aiosqlite

from datetime import datetime, timezone

from app.config import DB_PATH
from app.platforms.qq.life.sleep_engine import sleep_tick
from app.platforms.qq.life.activity_engine import activity_tick
from app.platforms.qq.life.life_state import (
    get_life_state,
    get_or_create_daily_cycle,
    evolve_life_values,
    update_life_state,
)

log = logging.getLogger(__name__)

# 每5分钟检查一次。
# 注意：这只是检查频率，不代表猫猫世界一次经过5分钟。
LIFE_TICK_SECONDS = 300

# 原 evolve_life_values() 的变化量以5分钟为一个标准单位。
BASE_STEP_SECONDS = 300.0


def _parse_utc(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value)
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


async def _get_elapsed_seconds():
    """
    返回从上一次生活演化到现在，现实真正经过的秒数。

    数据库存 UTC 时间。
    世界时间不由 tick 次数决定。
    """
    now_dt = datetime.now(timezone.utc)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT last_evolved_at
            FROM life_state
            WHERE id=1
            """
        )
        row = await cur.fetchone()

        previous = _parse_utc(
            row[0] if row else None
        )

        if previous is None:
            elapsed = BASE_STEP_SECONDS
        else:
            elapsed = (
                now_dt - previous
            ).total_seconds()

        # 系统时间异常回拨时，不允许产生负时间。
        elapsed = max(0.0, elapsed)

        await db.execute(
            """
            UPDATE life_state
            SET last_evolved_at=?
            WHERE id=1
            """,
            (now_dt.isoformat(),),
        )

        await db.commit()

    return elapsed


def _evolve_for_real_elapsed(
    *,
    energy,
    social_desire,
    phase,
    sleep_state,
    energy_baseline,
    social_baseline,
    elapsed_seconds,
):
    """
    按现实真正经过的时间演化状态。

    为保持原算法含义：
    原来的1次变化 = 现实5分钟。

    例如：
    300秒 -> 1个标准步长
    150秒 -> 0.5个标准步长
    900秒 -> 3个标准步长
    """

    steps = elapsed_seconds / BASE_STEP_SECONDS

    # 没有实际时间经过，就不改变状态。
    if steps <= 0:
        return {
            "energy": energy,
            "social_desire": social_desire,
        }

    # 拆成小步推进，避免长时间离线时
    # 基线回归计算出现明显失真。
    whole_steps = int(steps)
    fraction = steps - whole_steps

    values = {
        "energy": energy,
        "social_desire": social_desire,
    }

    # 防止异常系统时间导致无限循环。
    # 7天以上仍然承认现实时间已经过去，
    # 但数值状态最多逐步模拟7天，
    # 避免数据库损坏或系统时钟错误拖死进程。
    max_steps = 7 * 24 * 12
    whole_steps = min(
        whole_steps,
        max_steps,
    )

    for _ in range(whole_steps):
        values = evolve_life_values(
            energy=values["energy"],
            social_desire=values["social_desire"],
            phase=phase,
            sleep_state=sleep_state,
            energy_baseline=energy_baseline,
            social_baseline=social_baseline,
        )

    # 不足5分钟的部分按比例插值，
    # 保证时间流速不是5分钟一格。
    if fraction > 0:
        full = evolve_life_values(
            energy=values["energy"],
            social_desire=values["social_desire"],
            phase=phase,
            sleep_state=sleep_state,
            energy_baseline=energy_baseline,
            social_baseline=social_baseline,
        )

        values = {
            "energy": (
                values["energy"]
                + (
                    full["energy"]
                    - values["energy"]
                ) * fraction
            ),
            "social_desire": (
                values["social_desire"]
                + (
                    full["social_desire"]
                    - values["social_desire"]
                ) * fraction
            ),
        }

    return values


async def life_tick():
    # 先取得现实真正经过的时间。
    elapsed_seconds = await _get_elapsed_seconds()

    # 睡眠状态根据东京现实时间判断。
    sleep_result = await sleep_tick()

    action = sleep_result.get("action")
    phase = sleep_result.get("phase")

    if action != "no_change":
        log.info(
            "Cat life sleep action=%s phase=%s",
            action,
            phase,
        )

    # 活动持续时间本身使用真实时间戳。
    activity_result = await activity_tick(
        phase
    )

    life = await get_life_state()
    cycle = await get_or_create_daily_cycle()

    values = _evolve_for_real_elapsed(
        energy=life["energy"],
        social_desire=life["social_desire"],
        phase=phase,
        sleep_state=life["sleep_state"],
        energy_baseline=cycle["energy_baseline"],
        social_baseline=cycle["social_baseline"],
        elapsed_seconds=elapsed_seconds,
    )

    life = await update_life_state(
        energy=values["energy"],
        social_desire=values["social_desire"],
    )

    log.info(
        "Cat life tick real_elapsed=%.1fs phase=%s activity=%s",
        elapsed_seconds,
        phase,
        life.get("activity"),
    )

    return {
        "real_elapsed_seconds": elapsed_seconds,
        "sleep": sleep_result,
        "activity": activity_result,
        "life": life,
    }


async def life_loop():
    log.info(
        "Cat life loop started; real-time 1:1 clock enabled"
    )

    while True:
        try:
            await life_tick()

        except asyncio.CancelledError:
            raise

        except Exception:
            log.exception(
                "Cat life loop tick failed"
            )

        await asyncio.sleep(
            LIFE_TICK_SECONDS
        )
