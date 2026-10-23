"""SQLite-хранилище: одна асинхронная WAL-база с индексами под все горячие запросы."""
import json
import time
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS admins (
    user_id  INTEGER PRIMARY KEY,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    username   TEXT,
    type       TEXT NOT NULL,            -- group | supergroup | channel
    can_send   INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chats_type_title ON chats(type, title);
CREATE INDEX IF NOT EXISTS ix_chats_title ON chats(title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    entities   TEXT NOT NULL DEFAULT '[]', -- entities в формате Bot API (JSON)
    media_path TEXT,
    media_type TEXT,                       -- photo | video | animation | document | audio | voice
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 0,
    trigger    TEXT NOT NULL DEFAULT 'keywords', -- keywords | commands | any
    keywords   TEXT NOT NULL DEFAULT '[]',       -- [[слово, ...], [слово, ...]]: ИЛИ внутри группы, И между группами
    commands   TEXT NOT NULL DEFAULT '[]',       -- свои команды: ["/start", "/price", "старт"]
    exclude    TEXT NOT NULL DEFAULT '[]',       -- минус-слова
    notify     INTEGER NOT NULL DEFAULT 1,
    forward_to INTEGER,
    reply_tpl  INTEGER REFERENCES templates(id) ON DELETE SET NULL,
    dm_tpl     INTEGER REFERENCES templates(id) ON DELETE SET NULL,
    cooldown_h INTEGER NOT NULL DEFAULT 24,
    delay_sec  INTEGER,                          -- NULL = как у группы
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rules_enabled ON rules(enabled);

-- отслеживаемые группы со своими настройками
CREATE TABLE IF NOT EXISTS groups (
    chat_id   INTEGER PRIMARY KEY,
    enabled   INTEGER NOT NULL DEFAULT 1,
    delay_sec INTEGER NOT NULL DEFAULT 0,  -- пауза перед ответом / ЛС / пересылкой
    notify    INTEGER NOT NULL DEFAULT 1,
    added_at  INTEGER NOT NULL,
    bot_id    INTEGER                       -- бот заявок группы; NULL = реагировать на всех
);
CREATE INDEX IF NOT EXISTS ix_groups_enabled ON groups(enabled);

CREATE TABLE IF NOT EXISTS rule_sources (
    rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    PRIMARY KEY (rule_id, chat_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_rule_sources_chat ON rule_sources(chat_id);

CREATE TABLE IF NOT EXISTS broadcasts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 0,
    interval_min INTEGER NOT NULL DEFAULT 60,   -- 0 = только ручной запуск
    delay_sec    INTEGER NOT NULL DEFAULT 20,   -- пауза между чатами
    next_run_at  INTEGER NOT NULL DEFAULT 0,
    last_run_at  INTEGER,
    last_ok      INTEGER NOT NULL DEFAULT 0,
    last_fail    INTEGER NOT NULL DEFAULT 0,
    rotate_idx   INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_broadcasts_due ON broadcasts(enabled, next_run_at);

CREATE TABLE IF NOT EXISTS broadcast_templates (
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    template_id  INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    PRIMARY KEY (broadcast_id, template_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_bt_template ON broadcast_templates(template_id);

CREATE TABLE IF NOT EXISTS broadcast_targets (
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    chat_id      INTEGER NOT NULL,
    PRIMARY KEY (broadcast_id, chat_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_btg_chat ON broadcast_targets(chat_id);

CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     INTEGER,
    chat_id     INTEGER NOT NULL,
    msg_id      INTEGER NOT NULL,
    author_id   INTEGER,
    author_name TEXT,
    author_username TEXT,
    text        TEXT,
    created_at  INTEGER NOT NULL,
    UNIQUE (chat_id, msg_id, rule_id)
);
CREATE INDEX IF NOT EXISTS ix_leads_created ON leads(created_at);
CREATE INDEX IF NOT EXISTS ix_leads_rule_created ON leads(rule_id, created_at);

CREATE TABLE IF NOT EXISTS dm_log (
    user_id INTEGER PRIMARY KEY,
    rule_id INTEGER,
    sent_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_dm_log_sent ON dm_log(sent_at);

CREATE TABLE IF NOT EXISTS send_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_id INTEGER,
    chat_id      INTEGER NOT NULL,
    ok           INTEGER NOT NULL,
    error        TEXT,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_send_log_bc_created ON send_log(broadcast_id, created_at);
CREATE INDEX IF NOT EXISTS ix_send_log_created ON send_log(created_at);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "paused": False,
    "notify_leads": True,
    "dm_delay": 20,            # секунд между личными сообщениями авторам
    "quiet_hours": "",         # "23-8" — рассылки не идут в это время
    "link_preview": False,
    "retention_days": 30,      # сколько дней хранить журналы
    "tz_offset": 3,            # часовой пояс для тихих часов и статистики (UTC+3 — Москва)
    "main_menu": ["groups", "rules", "leads", "templates", "broadcasts", "chats", "pause"],
}


def now() -> int:
    return int(time.time())


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        for pragma in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA foreign_keys=ON",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA cache_size=-16000",
            "PRAGMA busy_timeout=5000",
        ):
            await self.conn.execute(pragma)
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        async with self.conn.execute("SELECT key, value FROM settings") as cur:
            async for row in cur:
                self.settings[row["key"]] = json.loads(row["value"])
        await self._migrate()

    async def _migrate(self) -> None:
        """Обновление баз, созданных прошлыми версиями."""
        cols = {r["name"] for r in await self.fetchall("PRAGMA table_info(rules)")}
        if "commands" not in cols:
            await self.conn.execute("ALTER TABLE rules ADD COLUMN commands TEXT NOT NULL DEFAULT '[]'")
        if "delay_sec" not in cols:
            await self.conn.execute("ALTER TABLE rules ADD COLUMN delay_sec INTEGER")
        gcols = {r["name"] for r in await self.fetchall("PRAGMA table_info(groups)")}
        if "bot_id" not in gcols:
            await self.conn.execute("ALTER TABLE groups ADD COLUMN bot_id INTEGER")
        await self.conn.execute(
            "UPDATE rules SET trigger = 'commands', commands = '[\"/start\"]' WHERE trigger = 'start'"
        )
        await self.conn.execute(
            "INSERT OR IGNORE INTO groups(chat_id, added_at) SELECT DISTINCT chat_id, ? FROM rule_sources",
            (now(),),
        )
        await self.conn.commit()
        menu = self.settings.get("main_menu")
        if not self.get("migr_groups"):
            if "groups" not in menu:
                await self.put("main_menu", ["groups", *menu])
            await self.put("migr_groups", True)

    async def close(self) -> None:
        if self.conn:
            await self.conn.execute("PRAGMA optimize")
            await self.conn.close()

    # --- низкоуровневые помощники ---

    async def execute(self, sql: str, params: Iterable = ()) -> int:
        cur = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        return cur.lastrowid

    async def executemany(self, sql: str, rows: Iterable[Iterable]) -> None:
        await self.conn.executemany(sql, rows)
        await self.conn.commit()

    async def fetchone(self, sql: str, params: Iterable = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, tuple(params)) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Iterable = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, tuple(params)) as cur:
            return list(await cur.fetchall())

    async def scalar(self, sql: str, params: Iterable = ()) -> Any:
        row = await self.fetchone(sql, params)
        return row[0] if row else None

    # --- настройки (кэшируются в памяти) ---

    def get(self, key: str) -> Any:
        return self.settings.get(key, DEFAULT_SETTINGS.get(key))

    async def put(self, key: str, value: Any) -> None:
        self.settings[key] = value
        await self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    # --- админы ---

    async def admin_ids(self) -> set[int]:
        rows = await self.fetchall("SELECT user_id FROM admins")
        return {r["user_id"] for r in rows}

    # --- чаты ---

    async def upsert_chats(self, chats: list[tuple[int, str, str | None, str, int]]) -> None:
        ts = now()
        await self.executemany(
            "INSERT INTO chats(id, title, username, type, can_send, updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, username=excluded.username, "
            "type=excluded.type, can_send=excluded.can_send, updated_at=excluded.updated_at",
            [(*c, ts) for c in chats],
        )

    async def chat_titles(self, ids: Iterable[int]) -> dict[int, str]:
        ids = list(ids)
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = await self.fetchall(f"SELECT id, title FROM chats WHERE id IN ({marks})", ids)
        return {r["id"]: r["title"] for r in rows}

    # --- шаблоны ---

    async def template(self, tid: int | None) -> aiosqlite.Row | None:
        if not tid:
            return None
        return await self.fetchone("SELECT * FROM templates WHERE id = ?", (tid,))

    # --- правила ---

    async def rule(self, rid: int) -> aiosqlite.Row | None:
        return await self.fetchone("SELECT * FROM rules WHERE id = ?", (rid,))

    async def rule_sources(self, rid: int) -> list[int]:
        rows = await self.fetchall("SELECT chat_id FROM rule_sources WHERE rule_id = ?", (rid,))
        return [r["chat_id"] for r in rows]

    async def group(self, chat_id: int) -> aiosqlite.Row | None:
        return await self.fetchone("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))

    async def add_group(self, chat_id: int) -> None:
        await self.execute("INSERT OR IGNORE INTO groups(chat_id, added_at) VALUES(?, ?)", (chat_id, now()))

    # --- рассылки ---

    async def broadcast(self, bid: int) -> aiosqlite.Row | None:
        return await self.fetchone("SELECT * FROM broadcasts WHERE id = ?", (bid,))

    async def broadcast_template_ids(self, bid: int) -> list[int]:
        rows = await self.fetchall(
            "SELECT template_id FROM broadcast_templates WHERE broadcast_id = ? ORDER BY template_id",
            (bid,),
        )
        return [r["template_id"] for r in rows]

    async def broadcast_targets(self, bid: int) -> list[int]:
        rows = await self.fetchall(
            "SELECT chat_id FROM broadcast_targets WHERE broadcast_id = ?", (bid,)
        )
        return [r["chat_id"] for r in rows]

    # --- обслуживание ---

    async def cleanup(self) -> None:
        border = now() - int(self.get("retention_days")) * 86400
        await self.conn.execute("DELETE FROM leads WHERE created_at < ?", (border,))
        await self.conn.execute("DELETE FROM send_log WHERE created_at < ?", (border,))
        await self.conn.execute("DELETE FROM dm_log WHERE sent_at < ?", (border,))
        await self.conn.commit()
        await self.conn.execute("PRAGMA optimize")
