import json
import re

from app.brain.deepseek import extract_json
from app.memory.filter import memory_value
from app.memory.candidates import add_candidate
from app.memory.promotion import evaluate_candidate


SYSTEM_PROMPT = """
你是人物长期记忆提取器，不是聊天机器人。

只提取说话者明确表达、适合长期保存的信息。

可以提取：
- 明确偏好
- 明确厌恶
- 称呼
- 长期兴趣
- 学习方向
- 长期习惯
- 相对稳定的个人事实

禁止：
- 猜测
- 心理分析
- 情绪推断
- 玩笑当事实
- 临时状态当长期事实
- 从一句模糊的话推断身份

只输出 JSON，不要解释，不要 Markdown。

没有可靠长期信息：
{"facts":[]}

有信息：
{"facts":[
  {
    "category":"preference",
    "key":"game",
    "value":"喜欢Minecraft",
    "confidence":0.95
  }
]}

confidence 必须在 0 到 1 之间。
"""


def clean_json(text):
    text = text.strip()

    # 兼容模型偶尔返回 ```json
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    return text.strip()


async def extract_memory_candidates(
    person_id,
    text,
    platform=None,
    chat_id=None,
    message_id=None
):
    if not memory_value(text):
        return []

    raw = await extract_json(
        SYSTEM_PROMPT,
        text
    )

    try:
        data = json.loads(clean_json(raw))
    except Exception:
        return []

    facts = data.get("facts", [])

    if not isinstance(facts, list):
        return []

    saved = []

    for fact in facts[:5]:
        if not isinstance(fact, dict):
            continue

        category = str(
            fact.get("category", "")
        ).strip()

        key = str(
            fact.get("key", "")
        ).strip()

        value = str(
            fact.get("value", "")
        ).strip()

        try:
            confidence = float(
                fact.get("confidence", 0.5)
            )
        except Exception:
            confidence = 0.5

        confidence = max(
            0.0,
            min(1.0, confidence)
        )

        if not category or not key or not value:
            continue

        # 太低置信度连候选都不保存
        if confidence < 0.70:
            continue

        candidate_id = await add_candidate(
            person_id=person_id,
            category=category[:50],
            fact_key=key[:100],
            fact_value=value[:500],
            confidence=confidence,
            source_platform=platform,
            source_chat_id=chat_id,
            source_message_id=message_id,
            source_text=text[:2000]
        )

        saved.append(candidate_id)

        # 每次出现新证据后重新评估。
        # 是否真正进入长期记忆由 promotion 策略决定。
        await evaluate_candidate(candidate_id)

    return saved
