import os

QQBOT_APP_ID = os.getenv("QQBOT_APP_ID", "").strip()
QQBOT_APP_SECRET = os.getenv("QQBOT_APP_SECRET", "").strip()

if not QQBOT_APP_ID:
    raise RuntimeError("QQBOT_APP_ID is not configured")

if not QQBOT_APP_SECRET:
    raise RuntimeError("QQBOT_APP_SECRET is not configured")
