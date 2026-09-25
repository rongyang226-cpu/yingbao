from __future__ import annotations

from datetime import datetime, timezone
import aiosqlite

from app.config import DB_PATH

POSES = {"stand","wave","clasp","lean","tilt","hair","heart","skirt","arms","sit"}
OUTFITS = {"moon","knit","blue","black","sleep"}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

async def init_appearance():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS mobile_appearance (
            person_id INTEGER PRIMARY KEY,
            pose_key TEXT NOT NULL DEFAULT 'stand',
            outfit_key TEXT NOT NULL DEFAULT 'moon',
            model_scale INTEGER NOT NULL DEFAULT 100,
            updated_at TEXT NOT NULL
        )
        """)
        await db.commit()

async def get_appearance(person_id: int):
    await init_appearance()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT pose_key,outfit_key,model_scale,updated_at FROM mobile_appearance WHERE person_id=?",
            (int(person_id),),
        )
        row = await cur.fetchone()
        if not row:
            t = now_iso()
            await db.execute(
                "INSERT INTO mobile_appearance(person_id,pose_key,outfit_key,model_scale,updated_at) VALUES(?,?,?,?,?)",
                (int(person_id),"stand","moon",100,t),
            )
            await db.commit()
            return {"pose":"stand","outfit":"moon","scale":100,"updated_at":t}
    return {"pose":row[0],"outfit":row[1],"scale":int(row[2]),"updated_at":row[3]}

async def set_appearance(person_id: int, *, pose=None, outfit=None, scale=None):
    current = await get_appearance(person_id)
    pose = current["pose"] if pose is None else str(pose)
    outfit = current["outfit"] if outfit is None else str(outfit)
    scale = current["scale"] if scale is None else int(scale)
    if pose not in POSES:
        raise ValueError("invalid_pose")
    if outfit not in OUTFITS:
        raise ValueError("invalid_outfit")
    scale = max(65, min(130, scale))
    t = now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO mobile_appearance(person_id,pose_key,outfit_key,model_scale,updated_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(person_id) DO UPDATE SET
          pose_key=excluded.pose_key,
          outfit_key=excluded.outfit_key,
          model_scale=excluded.model_scale,
          updated_at=excluded.updated_at
        """,(int(person_id),pose,outfit,scale,t))
        await db.commit()
    return {"pose":pose,"outfit":outfit,"scale":scale,"updated_at":t}
