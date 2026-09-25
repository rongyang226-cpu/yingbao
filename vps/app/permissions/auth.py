from app.config import TELEGRAM_OWNER_ID


OWNER = "OWNER"
ADMIN = "ADMIN"
USER = "USER"
GUEST = "GUEST"


def is_owner(
    platform: str,
    user_id
) -> bool:

    if platform != "telegram":
        return False

    return (
        str(user_id)
        == str(TELEGRAM_OWNER_ID)
    )


def get_role(
    platform: str,
    user_id
) -> str:

    if is_owner(
        platform,
        user_id
    ):
        return OWNER

    return USER


def require_owner(
    platform: str,
    user_id
) -> bool:

    return is_owner(
        platform,
        user_id
    )


CAPABILITIES = {
    OWNER: {
        "chat",
        "weather",
        "games",
        "own_reminders",
        "debug",
        "internal_status",
        "private_diary",
        "private_memory",
        "cross_scene_owner_memory",
        "manage_state",
    },
    USER: {
        "chat",
        "weather",
        "games",
        "own_reminders",
    },
    GUEST: {
        "chat",
    },
}


def can(platform: str, user_id, capability: str) -> bool:
    role = get_role(platform, user_id)
    return capability in CAPABILITIES.get(role, set())
