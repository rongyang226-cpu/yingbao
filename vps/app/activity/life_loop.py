import asyncio
import logging

from app.activity.sleep_engine import sleep_tick
from app.activity.activity_engine import activity_tick
from app.activity.consistency_guard import enforce_state_consistency
from app.activity.impulses import maintain_impulses
from app.activity.needs import evolve_needs
from app.activity.domestic import evolve_domestic, update_outfit
from app.tools.weather_cache import get_cached_weather
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

    consistency = await enforce_state_consistency()
    life = consistency["life"]

    try:
        needs = await evolve_needs(
            life=life,
        )
    except Exception:
        log.exception("Needs evolution failed")
        needs = None

    try:
        domestic = await evolve_domestic(
            life=life,
        )
        try:
            cached = await get_cached_weather("35.676,139.65")
            weather = cached.get("weather") if cached else None
        except Exception:
            weather = None
        await update_outfit(
            activity=life.get("activity") or "idle",
            weather=weather,
            sleep_state=life.get("sleep_state") or "awake",
        )
    except Exception:
        log.exception("Domestic evolution failed")
        domestic = None

    try:
        impulse_update = await maintain_impulses(
            life=life,
        )
    except Exception:
        log.exception("Impulse maintenance failed")
        impulse_update = None

    return {
        "sleep": sleep_result,
        "activity": activity_result,
        "life": life,
        "consistency": consistency,
        "needs": needs,
        "domestic": domestic,
        "impulse": impulse_update,
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
