"""Ядро юзербота: подключение Telethon, синхронизация чатов, отправка шаблонов."""
import asyncio
import logging
from html import escape
from typing import Awaitable, Callable

from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession
from telethon.tl import types

from ..config import Config
from ..db import Database
from .broadcaster import Broadcaster
from .formatting import to_telethon
from .monitor import Monitor

log = logging.getLogger(__name__)

EventCallback = Callable[[str], Awaitable[None]]
LeadCallback = Callable[[int], Awaitable[None]]

def make_session(cfg: Config):
    s = cfg.session
    if len(s) > 100:  # строковая сессия
        return StringSession(s)
    return str(cfg.data_dir / s)


def chat_kind(entity) -> str | None:
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel):
        return "supergroup" if entity.megagroup else "channel"
    return None


def can_send(entity) -> bool:
    if getattr(entity, "left", False) or getattr(entity, "deactivated", False):
        return False
    if getattr(entity, "creator", False) or getattr(entity, "admin_rights", None):
        if isinstance(entity, types.Channel) and entity.broadcast and not entity.creator:
            return bool(entity.admin_rights.post_messages)
        return True
    if isinstance(entity, types.Channel) and entity.broadcast:
        return False
    for rights in (getattr(entity, "banned_rights", None), getattr(entity, "default_banned_rights", None)):
        if rights and rights.send_messages:
            return False
    return True


# сессия отозвана или аккаунт заблокирован — переподключение не поможет
FATAL_ERRORS = (
    errors.AuthKeyUnregisteredError,
    errors.AuthKeyDuplicatedError,
    errors.SessionRevokedError,
    errors.UserDeactivatedBanError,
    errors.UserDeactivatedError,
)


class UserBot:
    def __init__(self, cfg: Config, db: Database):
        self.cfg = cfg
        self.db = db
        self.client = TelegramClient(
            make_session(cfg),
            cfg.api_id,
            cfg.api_hash,
            device_model="Admin Userbot",
            system_version="1.0",
            app_version="1.0",
            flood_sleep_threshold=60,
            receive_updates=True,
        )
        self.me: types.User | None = None
        self.on_event: EventCallback | None = None
        self.on_lead: LeadCallback | None = None
        self.monitor = Monitor(self)
        self.broadcaster = Broadcaster(self)
        self._tasks: set[asyncio.Task] = set()
        self.stopping = False

    @property
    def online(self) -> bool:
        return self.me is not None and self.client.is_connected()

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("Ошибка в фоновой задаче", exc_info=task.exception())

    async def event(self, text: str) -> None:
        if self.on_event:
            try:
                await self.on_event(text)
            except Exception:
                log.exception("Не удалось отправить уведомление админам")

    async def run(self) -> None:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.event(
                "⚠️ <b>Юзербот не авторизован.</b>\n"
                "Создайте сессию командой <code>python login.py</code> на сервере и перезапустите."
            )
            raise RuntimeError("Сессия юзербота не авторизована — запустите login.py")
        self.me = await self.client.get_me()
        log.info("Юзербот: %s (id %s)", utils.get_display_name(self.me), self.me.id)

        await self.monitor.setup()
        await self.event(f"🟢 Юзербот подключён: <b>{escape(utils.get_display_name(self.me))}</b>")
        self.spawn(self.refresh_dialogs())
        self.spawn(self.broadcaster.loop())
        self.spawn(self._maintenance())
        try:
            await self.client.run_until_disconnected()
        finally:
            self.me = None
            for task in list(self._tasks):
                task.cancel()

    async def stop(self) -> None:
        self.stopping = True
        await self.client.disconnect()

    async def _maintenance(self) -> None:
        while True:
            try:
                await self.db.cleanup()
            except Exception:
                log.exception("Ошибка очистки журналов")
            await asyncio.sleep(6 * 3600)

    async def refresh_dialogs(self) -> int:
        """Синхронизирует группы и каналы аккаунта в таблицу chats."""
        rows = []
        async for dialog in self.client.iter_dialogs():
            kind = chat_kind(dialog.entity)
            if not kind or getattr(dialog.entity, "left", False):
                continue
            rows.append((
                dialog.id,
                dialog.name or "Без названия",
                getattr(dialog.entity, "username", None),
                kind,
                int(can_send(dialog.entity)),
            ))
        if rows:
            await self.db.upsert_chats(rows)
            ids = [r[0] for r in rows]
            marks = ",".join("?" * len(ids))
            # чаты, из которых аккаунт вышел, больше не предлагаем
            await self.db.execute(f"DELETE FROM chats WHERE id NOT IN ({marks})", ids)
        log.info("Синхронизировано чатов: %s", len(rows))
        return len(rows)

    async def send_template(self, target, tpl, *, reply_to: int | None = None, media=None):
        """Отправляет шаблон. media — уже загруженное медиа для повторной отправки без аплоада."""
        entities = to_telethon(tpl["entities"])
        text = tpl["text"] or ""
        if tpl["media_path"]:
            kind = tpl["media_type"]
            return await self.client.send_file(
                target,
                media or tpl["media_path"],
                caption=text,
                formatting_entities=entities,
                reply_to=reply_to,
                voice_note=kind == "voice",
                supports_streaming=kind == "video",
                force_document=kind == "document",
            )
        return await self.client.send_message(
            target,
            text,
            formatting_entities=entities,
            reply_to=reply_to,
            link_preview=bool(self.db.get("link_preview")),
        )
