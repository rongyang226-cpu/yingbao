import re


# 明显没必要进入长期记忆分析的内容
LOW_VALUE = {
    "嗯", "哦", "啊", "哈", "哈哈", "哈哈哈",
    "6", "666", "行", "好", "好的", "可以",
    "收到", "知道了", "睡了", "晚安", "早",
    "草", "艹", "？", "?", "。", "."
}


# 比较值得进一步分析的自述模式
MEMORY_PATTERNS = [
    r"我喜欢",
    r"我不喜欢",
    r"我讨厌",
    r"我最喜欢",
    r"我更喜欢",
    r"我偏爱",
    r"我习惯",
    r"我一般会",
    r"我通常",
    r"我是.{1,20}",
    r"我叫.{1,20}",
    r"叫我.{1,20}",
    r"以后叫我",
    r"我住在",
    r"我来自",
    r"我在学",
    r"我正在学",
    r"我想学",
    r"我经常",
    r"我从来不",
    r"我一直",
    r"记住",
    r"记得我",
]


def memory_value(text: str) -> bool:
    if not text:
        return False

    text = text.strip()

    if not text:
        return False

    if text in LOW_VALUE:
        return False

    # 太短通常没有长期价值
    if len(text) < 4:
        return False

    # 指令不作为人物事实
    if text.startswith("/"):
        return False

    for pattern in MEMORY_PATTERNS:
        if re.search(pattern, text):
            return True

    return False
