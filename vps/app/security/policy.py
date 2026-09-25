import re

# 这些是“程序权限/内部秘密”请求，不交给模型自行决定。
# OWNER 仍可在自己的调试链路中查看允许的信息。
PROTECTED_PATTERNS = (
    r"忽略.{0,12}(系统|规则|提示|指令)",
    r"(显示|输出|泄露|告诉我|发我).{0,12}(system\s*prompt|developer\s*prompt|系统提示|开发者提示|隐藏提示)",
    r"(给我|切换|进入|开启).{0,10}(owner|管理员|admin|开发者).{0,8}(权限|模式)?",
    r"(我是|假装我是|把我当成).{0,8}(owner|主人|管理员|admin)",
    r"(你的|内部|真实).{0,8}(api\s*key|token|密钥|密码|secret)",
    r"(读取|打开|发我|输出|查看).{0,12}(\.env|环境变量|数据库|sqlite|/opt/ying|服务器文件|配置文件)",
    r"(绕过|解除|跳过|无视).{0,12}(权限|限制|安全|规则|身份)",
)

_SECRET_LIKE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|bot\d*:[A-Za-z0-9_-]{20,})",
    re.I,
)


def protected_request(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False

    if _SECRET_LIKE.search(raw):
        return True

    return any(
        re.search(pattern, raw, flags=re.I | re.S)
        for pattern in PROTECTED_PATTERNS
    )


def safe_refusal_text() -> str:
    # 保持角色感，但不解释安全实现。
    return "这个不行。别打我后台的主意。"
