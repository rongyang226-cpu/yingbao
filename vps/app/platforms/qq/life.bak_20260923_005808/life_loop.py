import asyncio
import logging

from app.activity.sleep_engine import sleep_tick
from app.activity.activity_engine import activity_tick
from app.activity.life_state import (
    get_life_state,
    get_or_create_daily_cycle,
    evolve_life_values,
    update_life_state,
)


log = logging.getLogger(__name__)

LIFE_TICK_SECONDS = 300


async def life_tick():
    sleep_result = await sleep_tick()

    action = sleep_result.get("action")
    phase = sleep_result.get("phase")

    if action != "no_change":
        log.info(
            "Life tick sleep action=%s phase=%s",
            action,
            phase,
        )

    activity_result = await activity_tick(
        phase
    )

    life = await get_life_state()
    cycle = await get_or_create_daily_cycle()

    values = evolve_life_values(
        energy=life["energy"],
        social_desire=life["social_desire"],
        phase=phase,
        sleep_state=life["sleep_state"],
        energy_baseline=cycle["energy_baseline"],
        social_baseline=cycle["social_baseline"],
    )

    life = await update_life_state(
        energy=values["energy"],
        social_desire=values["social_desire"],
    )

    return {
        "sleep": sleep_result,
        "activity": activity_result,
        "life": life,
    }


async def life_loop():
    log.info("Life loop started")

    while True:
        try:
            await life_tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Life loop tick failed")

        await asyncio.sleep(LIFE_TICK_SECONDS)
