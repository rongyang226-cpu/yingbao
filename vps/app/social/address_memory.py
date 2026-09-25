import re


_PATTERNS = [
    r"以后(?:就)?叫我(.+?)(?:吧|就行)?$",
    r"叫我(.+?)就行$",
    r"你可以叫我(.+?)(?:吧)?$",
]


def extract_preferred_address(text: str):
    text = text.strip()

    for pattern in _PATTERNS:
        match = re.search(pattern, text)
        if not match:
            continue

        value = match.group(1).strip()

        if not value:
            return None

        if len(value) > 12:
            return None

        return value

    return None


from app.social.profiles import add_fact


async def remember_preferred_address(
    *,
    person_id,
    text,
    source_platform=None,
    source_chat_id=None,
    source_message_id=None,
):
    value = extract_preferred_address(text)

    if not value:
        return None

    await add_fact(
        person_id=person_id,
        category="relationship",
        fact_key="preferred_address",
        fact_value=value,
        confidence=1.0,
        source_platform=source_platform,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
    )

    return value
