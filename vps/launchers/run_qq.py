import asyncio
import logging

from app.config import DB_PATH
from app.db import init_db
from app.social.people import init_people_db
from app.social.profiles import init_profile_db
from app.memory.candidates import init_candidate_db
from app.memory.events import init_events_db
from app.social.state import init_state_db

from app.platforms.qq.life.life_state import (
    init_life_state_db,
    init_daily_cycle_db,
)
from app.platforms.qq.life.life_loop import life_loop
from app.platforms.qq.bot import run_qq_listener


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def prepare():
    await init_db()
    await init_people_db()
    await init_profile_db()
    await init_candidate_db()
    await init_events_db()
    await init_state_db()

    # 猫猫使用自己的东京生活系统。
    await init_life_state_db()
    await init_daily_cycle_db()


async def main():
    await prepare()

    print("================================")
    print(" Cat QQ starting")
    print(" DB:", DB_PATH)
    print(" Life: Tokyo real-time 1:1")
    print("================================")

    life_task = asyncio.create_task(
        life_loop(),
        name="cat-life-loop",
    )

    try:
        await run_qq_listener()

    finally:
        life_task.cancel()

        try:
            await life_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
