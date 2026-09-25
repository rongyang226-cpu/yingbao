from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def digest(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def init_mobile_auth():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS mobile_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot TEXT NOT NULL UNIQUE,
            access_role TEXT NOT NULL,
            secret_hash TEXT NOT NULL UNIQUE,
            person_id INTEGER,
            bound_device_id TEXT UNIQUE,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mobile_device_sessions (
            device_id TEXT PRIMARY KEY,
            key_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            session_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        """)
        await db.commit()


async def create_blank_person(db):
    t = now_iso()
    cur = await db.execute(
        """INSERT INTO people(display_name, role, first_seen, last_seen)
           VALUES(NULL, 'USER', ?, ?)""",
        (t, t),
    )
    return int(cur.lastrowid)


async def bind_device(device_id: str, access_key: str):
    await init_mobile_auth()
    device_id = str(device_id or "").strip()
    access_key = str(access_key or "").strip()
    if not device_id or not access_key:
        return {"ok": False, "error": "missing_credentials"}

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT id, slot, access_role, person_id, bound_device_id
               FROM mobile_keys
               WHERE secret_hash=? AND active=1""",
            (digest(access_key),),
        )
        row = await cur.fetchone()
        if not row:
            return {"ok": False, "error": "invalid_key"}

        key_id, slot, access_role, person_id, bound_device_id = row
        if bound_device_id and str(bound_device_id) != device_id:
            return {"ok": False, "error": "key_already_bound"}

        # A physical device is permanently paired with its first key too.
        # We deliberately include revoked sessions here: reinstall/logout may
        # revoke a session, but it must never allow a different key/device pair.
        cur = await db.execute(
            """SELECT key_id, person_id FROM mobile_device_sessions
               WHERE device_id=?""",
            (device_id,),
        )
        existing = await cur.fetchone()
        if existing:
            if int(existing[0]) != int(key_id):
                return {"ok": False, "error": "device_already_bound"}
            if person_id is None:
                person_id = int(existing[1])
            session_secret = secrets.token_urlsafe(32)
            t = now_iso()
            await db.execute(
                """UPDATE mobile_device_sessions
                   SET person_id=?, session_hash=?, last_seen_at=?, revoked=0
                   WHERE device_id=?""",
                (person_id, digest(session_secret), t, device_id),
            )
            await db.commit()
            return {
                "ok": True,
                "session_secret": session_secret,
                "slot": slot,
                "access_role": access_role,
                "person_id": int(person_id),
            }

        if person_id is None:
            if slot == "OWNER":
                cur = await db.execute(
                    "SELECT person_id FROM people WHERE role='OWNER' ORDER BY person_id LIMIT 1"
                )
                owner = await cur.fetchone()
                if not owner:
                    return {"ok": False, "error": "owner_not_found"}
                person_id = int(owner[0])
            else:
                person_id = await create_blank_person(db)

        session_secret = secrets.token_urlsafe(32)
        t = now_iso()
        await db.execute(
            """UPDATE mobile_keys
               SET person_id=?, bound_device_id=?
               WHERE id=?""",
            (person_id, device_id, key_id),
        )
        await db.execute(
            """INSERT INTO mobile_device_sessions
               (device_id, key_id, person_id, session_hash,
                created_at, last_seen_at, revoked)
               VALUES(?,?,?,?,?,?,0)""",
            (device_id, key_id, person_id, digest(session_secret), t, t),
        )
        await db.commit()

    return {
        "ok": True,
        "session_secret": session_secret,
        "slot": slot,
        "access_role": access_role,
        "person_id": int(person_id),
    }


async def authenticate_device(device_id: str, session_secret: str):
    await init_mobile_auth()
    device_id = str(device_id or "").strip()
    session_secret = str(session_secret or "").strip()
    if not device_id or not session_secret:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT s.session_hash, s.person_id,
                      k.slot, k.access_role, k.active,
                      p.display_name, p.role
               FROM mobile_device_sessions s
               JOIN mobile_keys k ON k.id=s.key_id
               JOIN people p ON p.person_id=s.person_id
               WHERE s.device_id=? AND s.revoked=0""",
            (device_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None

        expected, person_id, slot, access_role, active, display_name, person_role = row
        if not int(active):
            return None
        if not secrets.compare_digest(expected, digest(session_secret)):
            return None

        await db.execute(
            "UPDATE mobile_device_sessions SET last_seen_at=? WHERE device_id=?",
            (now_iso(), device_id),
        )
        await db.commit()

    return {
        "person_id": int(person_id),
        "display_name": display_name,
        "person_role": person_role,
        "slot": slot,
        "access_role": access_role,
        "device_id": device_id,
    }


async def unbind_device(device_id: str):
    """Revoke only the current session; never release the permanent key/device lock."""
    await init_mobile_auth()
    device_id = str(device_id or "").strip()
    if not device_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT key_id FROM mobile_device_sessions WHERE device_id=?",
            (device_id,),
        )
        row = await cur.fetchone()
        if not row:
            return False
        await db.execute(
            "UPDATE mobile_device_sessions SET revoked=1 WHERE device_id=?",
            (device_id,),
        )
        # IMPORTANT: mobile_keys.bound_device_id is intentionally preserved.
        # The same key may be used again on this exact device, but never another.
        await db.commit()
    return True
