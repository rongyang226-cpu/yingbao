import re


RECALL_PATTERNS = [
    r"还记得",
    r"你记得",
    r"记不记得",
    r"之前.*说",
    r"以前.*说",
    r"以前.*聊",
    r"之前.*聊",
    r"上次.*说",
    r"上次.*聊",
    r"我以前",
    r"我之前",
    r"我们以前",
    r"我们之前",
]


def should_recall(text: str) -> bool:
    if not text:
        return False

    text = text.strip()

    return any(
        re.search(pattern, text)
        for pattern in RECALL_PATTERNS
    )


def extract_recall_query(text: str) -> str:
    """
    去掉常见的回忆触发词，
    留下更适合搜索的核心文本。
    """

    text = (text or "").strip()

    remove = [
        "你还记得",
        "还记得",
        "你记得",
        "记不记得",
        "我们以前",
        "我们之前",
        "我以前",
        "我之前",
        "之前",
        "以前",
        "上次",
        "吗",
        "？",
        "?"
    ]

    for x in remove:
        text = text.replace(x, " ")

    text = " ".join(text.split())

    return text[:100]
