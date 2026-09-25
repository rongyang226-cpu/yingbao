from datetime import datetime, timezone

import aiosqlite

from app.config import DB_PATH


def now():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def init_episodic_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS memory_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            scene TEXT NOT NULL,
            source_message_id INTEGER,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            salience REAL NOT NULL DEFAULT 0.5,
            privacy TEXT NOT NULL DEFAULT 'scoped',
            created_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(person_id)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_episodes_person
        ON memory_episodes(person_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_memory_episodes_scope
        ON memory_episodes(platform, chat_id, person_id, created_at);

        CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_episode_source
        ON memory_episodes(platform, chat_id, source_message_id)
        WHERE source_message_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS episodic_maintenance_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

        cur = await db.execute("PRAGMA table_info(memory_episodes)")
        cols = {row[1] for row in await cur.fetchall()}

        migrations = {
            "strength": "ALTER TABLE memory_episodes ADD COLUMN strength REAL NOT NULL DEFAULT 1.0",
            "recall_count": "ALTER TABLE memory_episodes ADD COLUMN recall_count INTEGER NOT NULL DEFAULT 0",
            "last_recalled_at": "ALTER TABLE memory_episodes ADD COLUMN last_recalled_at TEXT",
            "active": "ALTER TABLE memory_episodes ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
            "updated_at": "ALTER TABLE memory_episodes ADD COLUMN updated_at TEXT",
        }

        for col, sql in migrations.items():
            if col not in cols:
                await db.execute(sql)

        await db.execute(
            """
            UPDATE memory_episodes
            SET updated_at=COALESCE(updated_at, created_at)
            WHERE updated_at IS NULL
            """
        )
        await db.commit()


def episode_salience(text: str, *, owner=False) -> float:
    t = str(text or "").strip()
    if not t:
        return 0.0

    score = 0.20

    markers = (
        "记住", "别忘", "以后", "明天", "下次",
        "喜欢", "讨厌", "我叫", "我住", "我来自",
        "难受", "开心", "生气", "害怕", "委屈", "想你",
        "约好", "答应", "考试", "生日", "工作", "学习",
        "第一次", "最后一次", "重要", "以后我们", "还记得",
    )
    score += min(0.48, 0.08 * sum(1 for x in markers if x in t))

    # Short identity and emotional statements matter more than their length.
    if any(x in t for x in ("喜欢你", "害怕", "难受", "第一次", "约好", "答应", "生日")):
        score += 0.08
    if any(x in t for x in ("我叫", "可以叫我", "以后叫我")):
        score += 0.16
    if len(t) >= 20:
        score += 0.10
    if len(t) >= 60:
        score += 0.10
    if owner:
        score += 0.08

    return max(0.0, min(1.0, score))


def should_store_episode(text: str, *, owner=False) -> bool:
    t = str(text or "").strip()
    if len(t) < 4 or t.startswith("/"):
        return False

    score = episode_salience(t, owner=owner)
    return score >= (0.38 if owner else 0.46)


async def add_episode(
    *,
    person_id: int,
    platform: str,
    chat_id,
    scene: str,
    source_message_id,
    user_text: str,
    assistant_text: str,
    owner: bool = False,
):
    if not should_store_episode(user_text, owner=owner):
        return False

    await init_episodic_db()

    privacy = "owner_private" if owner and scene == "private" else "scoped"
    salience = episode_salience(user_text, owner=owner)
    t = now()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO memory_episodes (
                person_id, platform, chat_id, scene,
                source_message_id, user_text, assistant_text,
                salience, privacy, created_at,
                strength, recall_count, active, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, 0, 1, ?)
            """,
            (
                person_id,
                str(platform),
                str(chat_id),
                str(scene),
                source_message_id,
                user_text[:1200],
                assistant_text[:1200],
                salience,
                privacy,
                t,
                t,
            ),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_episode_context(
    *,
    person_id: int,
    platform: str,
    chat_id,
    scene: str,
    limit: int = 6,
):
    """
    严格按当前聊天范围读取。
    群A不会读取群B；群聊不会读取私聊。
    普通上下文注入不算“真正回忆”，因此不自动强化，
    避免同一批高分片段每轮都自我增强。
    """
    await init_episodic_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT
                id, user_text, assistant_text,
                salience, strength, recall_count,
                created_at
            FROM memory_episodes
            WHERE person_id=?
              AND platform=?
              AND chat_id=?
              AND scene=?
              AND active=1
            ORDER BY
                (salience * 0.72 + strength * 0.28) DESC,
                id DESC
            LIMIT ?
            """,
            (
                person_id,
                str(platform),
                str(chat_id),
                str(scene),
                int(limit),
            ),
        )
        rows = await cur.fetchall()

    if not rows:
        return "（暂无可靠的长期共同片段）"

    lines = []
    for (
        _eid,
        user_text,
        assistant_text,
        salience,
        strength,
        recall_count,
        created_at,
    ) in reversed(rows):
        lines.append(
            f"- 对方说过：{user_text[:240]} | 萤当时回复：{assistant_text[:240]}"
        )

    return "\n".join(lines)


async def maintain_episodic_memory():
    """
    渐进遗忘：
    - 30天内基本不衰减；
    - 高显著性/经常召回的片段更耐久；
    - 低显著性、长期没被召回的片段慢慢淡出；
    - 只 active=0，不物理删除。
    """
    await init_episodic_db()
    now_dt = datetime.now(timezone.utc)
    today = now_dt.date().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT value
            FROM episodic_maintenance_state
            WHERE key='last_daily_run'
            """
        )
        row = await cur.fetchone()

        if row and row[0] == today:
            return {
                "weakened": 0,
                "faded": 0,
                "skipped": True,
            }

        cur = await db.execute(
            """
            SELECT
                id, salience, strength,
                recall_count, last_recalled_at,
                created_at
            FROM memory_episodes
            WHERE active=1
            """
        )
        rows = await cur.fetchall()

        weakened = 0
        faded = 0

        for (
            eid,
            salience,
            strength,
            recall_count,
            last_recalled_at,
            created_at,
        ) in rows:
            salience = float(salience or 0.5)
            strength = float(strength or 1.0)
            recall_count = int(recall_count or 0)

            anchor = (
                _parse_dt(last_recalled_at)
                or _parse_dt(created_at)
            )
            if not anchor:
                continue

            age_days = (
                now_dt - anchor
            ).total_seconds() / 86400

            if age_days <= 30:
                continue

            # 重要/常被回忆的共同经历保留得更久。
            if salience >= 0.85 or recall_count >= 8:
                decay = 0.0007
            elif salience >= 0.65 or recall_count >= 4:
                decay = 0.002
            elif age_days <= 90:
                decay = 0.004
            else:
                decay = 0.007

            new_strength = max(0.0, strength - decay)

            should_fade = (
                age_days >= 120
                and new_strength < 0.30
                and salience < 0.72
                and recall_count < 4
            )

            if should_fade:
                await db.execute(
                    """
                    UPDATE memory_episodes
                    SET strength=?,
                        active=0,
                        updated_at=?
                    WHERE id=?
                    """,
                    (new_strength, now_dt.isoformat(), eid),
                )
                faded += 1
            elif new_strength != strength:
                await db.execute(
                    """
                    UPDATE memory_episodes
                    SET strength=?,
                        updated_at=?
                    WHERE id=?
                    """,
                    (new_strength, now_dt.isoformat(), eid),
                )
                weakened += 1

        await db.execute(
            """
            INSERT INTO episodic_maintenance_state(key, value)
            VALUES ('last_daily_run', ?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (today,),
        )
        await db.commit()

    return {
        "weakened": weakened,
        "faded": faded,
        "skipped": False,
    }
