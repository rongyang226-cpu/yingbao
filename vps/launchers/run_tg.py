import asyncio
import logging

from app.config import validate, DB_PATH
from app.db import init_db
from app.social.people import init_people_db
from app.social.profiles import init_profile_db
from app.memory.candidates import init_candidate_db
from app.memory.events import init_events_db
from app.social.state import init_state_db
from app.activity.life_state import (
    init_life_state_db,
    init_daily_cycle_db,
)
from app.platforms.telegram_bot import build_application
from app.activity.consistency_guard import enforce_state_consistency


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def prepare():
    validate()

    await init_db()
    await init_people_db()
    await init_profile_db()
    await init_candidate_db()
    await init_events_db()
    await init_state_db()
    await init_life_state_db()
    await init_daily_cycle_db()
    await enforce_state_consistency()


def main():
    asyncio.run(prepare())

    print("================================")
    print(" Ying Telegram starting")
    print(" DB:", DB_PATH)
    print("================================")

    app = build_application()

    app.run_polling(
        allowed_updates=["message"]
    )


if __name__ == "__main__":
    main()
