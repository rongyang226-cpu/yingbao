import json
from pathlib import Path


QQ_OWNER_ID = "913565158"

STATE_FILE = Path(
    "/opt/ying/data/qq_permissions.json"
)

ROLE_OWNER = "OWNER"
ROLE_VIEWER = "VIEWER"
ROLE_NORMAL = "NORMAL"


def _load():
    if not STATE_FILE.exists():
        return {
            "roles": {}
        }

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        data = {
            "roles": {}
        }

    if not isinstance(
        data.get("roles"),
        dict,
    ):
        data["roles"] = {}

    return data


def _save(data):
    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def get_qq_role(user_id):
    uid = str(user_id)

    if uid == QQ_OWNER_ID:
        return ROLE_OWNER

    data = _load()

    role = str(
        data["roles"].get(uid)
        or ROLE_NORMAL
    ).upper()

    if role not in {
        ROLE_VIEWER,
        ROLE_NORMAL,
    }:
        return ROLE_NORMAL

    return role


def set_qq_role(
    operator_id,
    target_user_id,
    role,
):
    operator = str(operator_id)
    target = str(target_user_id)
    role = str(role).upper()

    if operator != QQ_OWNER_ID:
        return False, "只有洛洛可以改权限。"

    if target == QQ_OWNER_ID:
        return False, "OWNER权限不能修改。"

    if role not in {
        ROLE_VIEWER,
        ROLE_NORMAL,
    }:
        return False, "不支持这个权限等级。"

    data = _load()

    if role == ROLE_NORMAL:
        data["roles"].pop(
            target,
            None,
        )
    else:
        data["roles"][target] = role

    _save(data)

    return True, role


def list_qq_roles(
    operator_id,
):
    if str(operator_id) != QQ_OWNER_ID:
        return None

    data = _load()

    result = {
        QQ_OWNER_ID: ROLE_OWNER
    }

    for uid, role in (
        data.get("roles")
        or {}
    ).items():
        result[str(uid)] = str(role)

    return result


def can_view_sensitive(user_id):
    return get_qq_role(
        user_id
    ) in {
        ROLE_OWNER,
        ROLE_VIEWER,
    }


def can_modify_core(user_id):
    return (
        get_qq_role(user_id)
        == ROLE_OWNER
    )


def can_publish_qzone(user_id):
    return (
        get_qq_role(user_id)
        == ROLE_OWNER
    )


def can_manage_permissions(user_id):
    return (
        get_qq_role(user_id)
        == ROLE_OWNER
    )


def can_chat(user_id):
    return True


def can_view(user_id):
    return get_qq_role(user_id) in {
        ROLE_OWNER,
        ROLE_VIEWER,
        ROLE_NORMAL,
    }


def can_modify_memory(user_id):
    return get_qq_role(user_id) == ROLE_OWNER


def can_modify_settings(user_id):
    return get_qq_role(user_id) == ROLE_OWNER


def can_manage_qzone(user_id):
    return get_qq_role(user_id) == ROLE_OWNER


def can_manage_core(user_id):
    return get_qq_role(user_id) == ROLE_OWNER
