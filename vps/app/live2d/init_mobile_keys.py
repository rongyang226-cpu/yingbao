from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from pathlib import Path

import aiosqlite

from app.config import DB_PATH
from app.live2d.mobile_auth import init_mobile_auth, now_iso

OUT = Path("/opt/ying/secrets/mobile_access_keys.json")
SLOTS = [
    ("OWNER", "OWNER"),
    ("ADMIN_1", "ADMIN"),
    ("ADMIN_2", "ADMIN"),
    ("USER_1", "USER"),
    ("USER_2", "USER"),
    ("USER_3", "USER"),
    ("USER_4", "USER"),
    ("USER_5", "USER"),
    ("USER_6", "USER"),
    ("USER_7", "USER"),
]


async def main():
    await init_mobile_auth()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM mobile_keys")
        count = int((await cur.fetchone())[0])
        if count:
            print(f"existing_keys={count}")
            return

        cur = await db.execute(
            "SELECT person_id FROM people WHERE role='OWNER' ORDER BY person_id LIMIT 1"
        )
        owner = await cur.fetchone()
        if not owner:
            raise RuntimeError("OWNER not found")
        plain = {}
        for slot, access_role in SLOTS:
            secret = "YB-" + secrets.token_urlsafe(36)
            plain[slot] = secret
            person_id = int(owner[0]) if slot == "OWNER" else None
            await db.execute(
                """INSERT INTO mobile_keys
                   (slot, access_role, secret_hash, person_id,
                    bound_device_id, active, created_at)
                   VALUES(?,?,?,?,NULL,1,?)""",
                (
                    slot,
                    access_role,
                    hashlib.sha256(secret.encode("utf-8")).hexdigest(),
                    person_id,
                    now_iso(),
                ),
            )
        await db.commit()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(plain, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT.chmod(0o600)
    print("created=10")
    print("key_file=" + str(OUT))


if __name__ == "__main__":
    asyncio.run(main())
