CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def parse_cn_number(text: str):
    """
    支持：
    一 -> 1
    两 -> 2
    十 -> 10
    十五 -> 15
    二十 -> 20
    二十五 -> 25
    九十九 -> 99

    阿拉伯数字直接返回 int。
    """
    text = text.strip()

    if text.isdigit():
        return int(text)

    if text in CN_DIGITS:
        return CN_DIGITS[text]

    if text == "十":
        return 10

    if "十" in text:
        left, right = text.split("十", 1)

        tens = (
            CN_DIGITS.get(left)
            if left
            else 1
        )

        ones = (
            CN_DIGITS.get(right)
            if right
            else 0
        )

        if tens is None or ones is None:
            return None

        return tens * 10 + ones

    return None
