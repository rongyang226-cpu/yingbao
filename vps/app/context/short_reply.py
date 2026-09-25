"""Keep a brief affirmative tied to the assistant's latest question."""

import re


_AFFIRMATIVE = re.compile(
    r"^(?:想|想啊|想呀|想的|要|要啊|要呀|好|好的|好呀|好啊|嗯|嗯嗯|是|是的|可以|当然)[！!。~～ ]*$"
)


def short_reply_hint(text: str, history: list[dict]) -> str:
    if not _AFFIRMATIVE.fullmatch(str(text or "").strip()):
        return ""
    if not history or history[-1].get("role") != "assistant":
        return ""
    last = str(history[-1].get("content") or "").strip()
    if not last or not any(mark in last for mark in ("?", "？", "想不想", "要不要")):
        return ""
    return (
        "\n\n【本轮简短回答】\n"
        "用户这句是在回答你上一条消息里的问题；先根据最近对话判断指向什么，"
        "承接原话题自然回应。不要说用户只回了一个字、让用户说完整，"
        "也不要凭空许诺能展示尚未准备好的图片。\n"
    )
