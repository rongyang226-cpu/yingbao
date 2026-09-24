import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path("/opt/ying")
ENV_FILE = BASE_DIR / ".env"
DB_PATH = Path(
    os.getenv(
        "YING_DB_PATH",
        str(BASE_DIR / "data" / "ying.db")
    )
).expanduser()

load_dotenv(ENV_FILE)

DEEPSEEK_API_KEY = os.getenv(
    "DEEPSEEK_API_KEY", ""
).strip()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", ""
).strip()

TELEGRAM_OWNER_ID = int(
    os.getenv("TELEGRAM_OWNER_ID", "0") or 0
)

DEEPSEEK_BASE_URL = os.getenv(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com"
).rstrip("/")

DEEPSEEK_MODEL = os.getenv(
    "DEEPSEEK_MODEL",
    "deepseek-chat"
).strip()

GROUP_REPLY_PROBABILITY = 0.30


def validate():
    missing = []

    if not DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_OWNER_ID:
        missing.append("TELEGRAM_OWNER_ID")

    if missing:
        raise RuntimeError(
            "缺少配置: " + ", ".join(missing)
        )

TELEGRAM_PROXY_URL = os.getenv(
    "TELEGRAM_PROXY_URL",
    ""
).strip()

# ===== Time =====
YING_TIMEZONE = os.getenv(
    "YING_TIMEZONE",
    "Asia/Shanghai"
)
