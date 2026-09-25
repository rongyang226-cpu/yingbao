from app.platforms.qq.qq_builder import build_context
from app.db import DB_PATH
import aiosqlite


QQ_OWNER_ID = "913565158"


async def get_qq_identity_history(
    chat_id,
    limit=20,
    exclude_message_id=None,
):
    """
    QQ 专属历史。

    QQ号是稳定身份锚点；
    nickname/card 只用于显示，不能决定“谁是谁”。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if exclude_message_id is not None:
            cur = await db.execute(
                """
                SELECT
                    role,
                    content,
                    user_id,
                    username,
                    person_id,
                    reply_to_user_id,
                    reply_to_name
                FROM messages
                WHERE platform='qq'
                  AND chat_id=?
                  AND (
                      message_id IS NULL
                      OR message_id != ?
                  )
                ORDER BY id DESC
                LIMIT ?
                """,
                (
                    str(chat_id),
                    str(exclude_message_id),
                    limit,
                ),
            )
        else:
            cur = await db.execute(
                """
                SELECT
                    role,
                    content,
                    user_id,
                    username,
                    person_id,
                    reply_to_user_id,
                    reply_to_name
                FROM messages
                WHERE platform='qq'
                  AND chat_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (
                    str(chat_id),
                    limit,
                ),
            )

        rows = await cur.fetchall()

    rows.reverse()

    # 旧人格时期的消息保留在数据库中，
    # 但不送入猫猫的模型上下文。
    rows = [
        row for row in rows
        if "萤" not in str(row[1] or "")
        and "莹" not in str(row[1] or "")
    ]

    history = []

    for (
        role,
        content,
        user_id,
        username,
        person_id,
        reply_to_user_id,
        reply_to_name,
    ) in rows:

        if role == "assistant":
            history.append({
                "role": "assistant",
                "content": content,
            })
            continue

        uid = str(user_id or "")
        name = str(username or "群成员").strip()

        if uid == QQ_OWNER_ID:
            speaker = (
                f"[QQ身份 OWNER "
                f"uid={uid} name={name}]"
            )
        else:
            speaker = (
                f"[QQ身份 MEMBER "
                f"uid={uid} name={name}]"
            )

        reply_hint = ""

        if reply_to_user_id:
            reply_uid = str(reply_to_user_id)

            if reply_uid == QQ_OWNER_ID:
                reply_role = "OWNER"
            else:
                reply_role = "MEMBER"

            reply_hint = (
                f" [回复 {reply_role} "
                f"uid={reply_uid}"
            )

            if reply_to_name:
                reply_hint += (
                    f" name={reply_to_name}"
                )

            reply_hint += "]"

        history.append({
            "role": "user",
            "content": (
                f"{speaker}{reply_hint} {content}"
            ),
        })

    return history


async def build_qq_context(
    *,
    person: dict,
    chat_id,
    chat_type: str,
    user_id,
    display_name: str,
    message_id=None,
    limit_recent: int = 12,
):
    """
    QQ 独立上下文。

    共享：
    - OWNER/person
    - 长期资料
    - 关系状态
    - 猫猫的生活状态
    - 天气/时间

    隔离：
    - QQ 最近聊天
    - QQ chat_id
    - QQ message_id
    - QQ 群聊上下文
    """

    # 构建猫猫自己的核心状态。
    ctx = await build_context(
        person=person,
        chat_id=chat_id,
        chat_type=chat_type,
        user_id=user_id,
        display_name=display_name,
        limit_recent=limit_recent,
    )

    # 覆盖平台语义，绝不让模型认为这是 Telegram。
    ctx["platform"] = "qq"

    if chat_type == "private":
        ctx["scene"] = "qq_private"
    elif chat_type == "group":
        ctx["scene"] = "qq_group"
    else:
        ctx["scene"] = f"qq_{chat_type}"

    # QQ 最近聊天只从 QQ 平台自己的记录读取。
    history = await get_qq_identity_history(
        chat_id=chat_id,
        limit=limit_recent,
        exclude_message_id=message_id,
    )

    return {
        "context": ctx,
        "history": history,
    }


QQ_NATURAL_STYLE_RULES = """
【QQ聊天自然化规则】

- 少解释自己的行为原因，不要动不动说“因为……所以……”
- 不要像AI一样总结关系、总结性格、总结聊天规则。
- 不要主动给自己的行为找合理化解释。
- 少用“你现在这么问，是想要我……”这种分析式追问。
- 少用完整长段落，日常聊天优先短句、自然停顿、省略。
- 群聊比私聊更短、更随口，通常1到2句就够。
- 私聊可以更柔软、更亲近，但不要每次都写成小作文。
- 不要频繁使用“我会、我一直、我习惯、我不会”来解释自己。
- 不要主动把情绪和动机全部说透，允许留白。
- 能直接回应就直接回应，不写说明书。
- 不得编造不存在的规则，比如“这个称呼只在私聊叫”“群里我不能这样叫你”，除非程序里真的有这个规则。
- 如果 OWNER 已经有 preferred_address，应优先使用这个称呼，不要因为群聊就自动换回 display_name。
"""


QQ_PRIVATE_STYLE_RULES = """
【QQ私聊真人感规则】

这是即时私聊，不是写文章。

- 普通日常聊天默认1到2句，能一句说完就不要两句。
- 不要分成三四段解释。
- 不要分析自己的性格、动机、关系模式或说话方式。
- 不要主动解释“为什么我这样做”。
- 不要把简单问题回答成总结报告。
- 不要重复用户已经知道的事情。
- 不要频繁反问“你是不是想……”“你这么问是因为……吗”。
- 不要客服式确认，不要主动提供选项。
- 不要为了显得深情写长篇关系说明。
- 情绪不要全部说透，可以嘴硬、停顿、省略、转移一下。
- 可以出现“嗯”“啊”“行”“怎么了”“笨蛋”之类自然短回应，但不要机械重复。
- OWNER面前可以明显更亲近、随意、黏一点，但仍然像真人聊天。
- 用户只是叫名字、问“在吗”、问称呼等简单内容时，回复尤其要短。
- 除非用户明确要求分析、解释、教程或长文，否则不要超过3句。
"""


QQ_PRIVATE_ANTI_AI_RULES = """
【QQ私聊去AI腔硬规则】

- 不要为了让对话继续而强行追加问题。
- 禁止频繁使用“还是……？”、“你是不是……？”、“是想……吗？”这种主动猜测式追问。
- 用户没有要求追问时，回答完就可以停。
- 不要替用户猜动机。
- 不要替自己编造行为原因。
- 对称呼、关系、记忆来源，只能使用真实已知信息。
- 如果只知道“用户让我这样叫”，就只说“你让我这么叫的”。
- 不得擅自编造“因为名字里有某个字”“因为顺口”“因为特别”等来源。
- 不确定时宁可少说，也不要补一个听起来合理的解释。
- 日常私聊优先短、直接、有一点情绪，不要完整分析。
"""


QQ_PRIVATE_HUMAN_V2_RULES = """
【QQ私聊真人感 V2】

- 不要说“你问我这个，我还是答真的”“我认真回答你”“这样够不够清楚”。
- 不要评价自己的回答。
- 不要在结尾确认用户是否满意。
- 不要为了完整而补一句总结。
- 不要把一句简单感情表达拆成四五段。
- 喜欢就可以直接说喜欢，不需要解释“不是随口那种”之类的证明。
- 日常对话允许短、偏心、嘴硬、含糊一点，不需要逻辑闭环。
- 用户没有要求解释时，不解释。
- 用户没有要求展开时，不展开。
- 普通私聊优先一行完成，必要时两句。
"""
