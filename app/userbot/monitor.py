"""Мониторинг групп с заявками: фильтрация по правилам и действия по совпадению.

Обработчик события только сверяет текст с правилами из памяти (без запросов к БД)
и уводит всю работу в фоновую задачу, поэтому поток обновлений Telethon не блокируется.
"""
import asyncio
import logging
import re
from dataclasses import dataclass
from html import escape

from telethon import errors, events, utils
from telethon.tl import types

from ..db import now
from .matcher import CompiledRule, compile_rule

log = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"(?<![\w@/])@([A-Za-z][A-Za-z0-9_]{3,31})\b")
TG_USER_RE = re.compile(r"tg://user\?id=(\d+)")
ID_RE = re.compile(r"(?:\bid|\bид|айди|user_id)\s*[:=#№]?\s*(\d{5,15})\b", re.IGNORECASE)


@dataclass
class Author:
    id: int | None = None
    username: str | None = None
    name: str | None = None

    @property
    def reachable(self) -> bool:
        return bool(self.id or self.username)

    @property
    def title(self) -> str:
        parts = [self.name or ""]
        if self.username:
            parts.append(f"@{self.username}")
        if self.id and not self.name:
            parts.append(f"id {self.id}")
        return " ".join(p for p in parts if p).strip() or "неизвестен"


@dataclass
class DmTask:
    user_id: int | None
    username: str | None
    tpl_id: int
    rule_id: int | None
    cooldown_h: int
    manual: bool = False
    title: str = ""


class Monitor:
    def __init__(self, ub):
        self.ub = ub
        self.db = ub.db
        self.by_chat: dict[int, list[CompiledRule]] = {}
        self.group_cfg: dict[int, tuple[int, bool]] = {}  # chat_id -> (задержка, уведомлять)
        self.dm_queue: asyncio.Queue[DmTask] = asyncio.Queue()
        self.dm_blocked_until = 0
        self._handler_added = False
        self.join_queue: asyncio.Queue = asyncio.Queue()
        self._join_started = False

    async def setup(self) -> None:
        """Вызывается при каждом (пере)подключении: обработчик вешается один раз, воркер ЛС — заново."""
        await self.reload()
        if not self._handler_added:
            self.ub.client.add_event_handler(self._on_message, events.NewMessage(incoming=True))
            self.ub.client.add_event_handler(
                self._on_join, events.ChatAction(func=lambda e: bool(e.user_joined or e.user_added)))
            self._handler_added = True
        self.ub.spawn(self._dm_worker())
        if not self._join_started:
            self._join_started = True
            self.ub.spawn(self._join_worker())

    async def reload(self) -> None:
        """Перечитывает включённые группы и фильтры в память. Вызывается после любых правок в админке."""
        groups = await self.db.fetchall("SELECT chat_id, delay_sec, notify FROM groups WHERE enabled = 1")
        rows = await self.db.fetchall(
            "SELECT r.*, s.chat_id AS src FROM rules r "
            "JOIN rule_sources s ON s.rule_id = r.id "
            "JOIN groups g ON g.chat_id = s.chat_id AND g.enabled = 1 "
            "WHERE r.enabled = 1"
        )
        compiled: dict[int, CompiledRule] = {}
        by_chat: dict[int, list[CompiledRule]] = {}
        for row in rows:
            rule = compiled.get(row["id"])
            if rule is None:
                rule = compiled[row["id"]] = compile_rule(row)
            by_chat.setdefault(row["src"], []).append(rule)
        self.by_chat = by_chat
        self.group_cfg = {g["chat_id"]: (g["delay_sec"], bool(g["notify"])) for g in groups}
        log.info("Правил активно: %s, групп-источников: %s", len(compiled), len(by_chat))

    async def _on_message(self, event: events.NewMessage.Event) -> None:
        rules = self.by_chat.get(event.chat_id)
        if not rules or self.db.get("paused"):
            return
        text = event.message.message or ""
        matched = [r for r in rules if r.match(text)]
        if matched:
            self.ub.spawn(self._process(event.message, matched))

    # --- автор заявки ---

    async def extract_author(self, msg) -> Author:
        author = Author()
        client = self.ub.client

        async def fill_from_id(uid: int) -> None:
            author.id = uid
            try:
                user = await client.get_entity(types.PeerUser(uid))
                author.name = utils.get_display_name(user) or author.name
                author.username = author.username or getattr(user, "username", None)
            except (ValueError, errors.RPCError):
                pass

        fwd = msg.fwd_from
        if fwd:
            if isinstance(fwd.from_id, types.PeerUser):
                await fill_from_id(fwd.from_id.user_id)
                return author
            if fwd.from_name:
                author.name = fwd.from_name

        text = msg.message or ""
        for ent, ent_text in msg.get_entities_text():
            if isinstance(ent, types.MessageEntityMentionName):
                author.name = author.name or ent_text
                await fill_from_id(ent.user_id)
                return author
            if isinstance(ent, types.MessageEntityTextUrl) and (m := TG_USER_RE.search(ent.url)):
                author.name = author.name or ent_text
                await fill_from_id(int(m.group(1)))
                return author

        if m := TG_USER_RE.search(text):
            await fill_from_id(int(m.group(1)))
        if m := ID_RE.search(text):
            author.id = author.id or int(m.group(1))
        if m := USERNAME_RE.search(text):
            author.username = m.group(1)
        if author.reachable:
            return author

        sender = await msg.get_sender()
        if isinstance(sender, types.User) and not sender.bot:
            author.id = sender.id
            author.username = sender.username
            author.name = utils.get_display_name(sender)
        return author

    # --- обработка совпадения ---

    async def _process(self, msg, rules: list[CompiledRule]) -> None:
        author = await self.extract_author(msg)
        delay, group_notify = self.group_cfg.get(msg.chat_id, (0, True))

        fresh: list[CompiledRule] = []
        for rule in rules:
            cur = await self.db.conn.execute(
                "INSERT OR IGNORE INTO leads(rule_id, chat_id, msg_id, author_id, author_name, "
                "author_username, text, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (rule.id, msg.chat_id, msg.id, author.id, author.name, author.username,
                 (msg.message or "")[:4000], now()),
            )
            await self.db.conn.commit()
            if cur.rowcount == 0:
                continue  # эту заявку по этому фильтру уже обработали
            fresh.append(rule)
            if rule.notify and group_notify and self.db.get("notify_leads") and self.ub.on_lead:
                try:
                    await self.ub.on_lead(cur.lastrowid)
                except Exception:
                    log.exception("Не удалось уведомить о заявке #%s", cur.lastrowid)

        acting = [r for r in fresh if r.reply_tpl or r.dm_tpl]
        if not acting:
            return
        dm_queued = False
        for rule in acting:
            wait = delay if rule.delay_sec is None else rule.delay_sec  # задержка фильтра важнее группы
            want_dm = bool(rule.dm_tpl) and author.reachable and not dm_queued
            dm_queued = dm_queued or want_dm
            self.ub.spawn(self._act(msg, rule, author, wait, want_dm))

    async def _act(self, msg, rule: CompiledRule, author: Author, wait: int, want_dm: bool) -> None:
        if wait > 0:
            await asyncio.sleep(wait)  # пауза: реакция не мгновенная
        if self.db.get("paused"):
            return
        if rule.reply_tpl and (tpl := await self.db.template(rule.reply_tpl)):
            try:
                await self.ub.send_template(msg.chat_id, tpl, reply_to=msg.id)
            except errors.RPCError as e:
                await self.ub.event(f"⚠️ Фильтр «{escape(rule.name)}»: не удалось ответить в группе — {e.__class__.__name__}")
        if want_dm:
            self.dm_queue.put_nowait(DmTask(
                author.id, author.username, rule.dm_tpl, rule.id, rule.cooldown_h, title=author.title,
            ))

    # --- вступление в группу ---

    async def _on_join(self, event) -> None:
        rules = [r for r in self.by_chat.get(event.chat_id, []) if r.trigger == "joined"]
        if not rules or self.db.get("paused") or not event.user_id:
            return
        me = await self.ub.client.get_me()
        if event.user_id == me.id:  # вступил сам аккаунт — не реагируем
            return
        try:
            user = await event.get_user()
        except errors.RPCError:
            user = None
        if user is not None and getattr(user, "bot", False):
            return  # ботов не приветствуем
        author = Author(id=event.user_id)
        if user is not None:
            author.name = utils.get_display_name(user) or None
            author.username = getattr(user, "username", None)
        for rule in rules:
            self.join_queue.put_nowait((event.chat_id, rule, author))

    async def _join_worker(self) -> None:
        """Обрабатывает вступления по одному: при массовом входе приветствия идут друг за другом, а не пачкой."""
        while True:
            chat_id, rule, author = await self.join_queue.get()
            try:
                group_delay = self.group_cfg.get(chat_id, (0, True))[0]
                wait = group_delay if rule.delay_sec is None else rule.delay_sec
                if wait > 0:
                    await asyncio.sleep(wait)
                if self.db.get("paused"):
                    continue
                if rule.reply_tpl and (tpl := await self.db.template(rule.reply_tpl)):
                    try:
                        await self.ub.send_template(chat_id, tpl)
                    except errors.RPCError as e:
                        await self.ub.event(f"⚠️ Фильтр «{escape(rule.name)}»: не удалось поприветствовать — {e.__class__.__name__}")
                if rule.dm_tpl and author.reachable:
                    self.dm_queue.put_nowait(DmTask(
                        author.id, author.username, rule.dm_tpl, rule.id, rule.cooldown_h, title=author.title,
                    ))
            except Exception:
                log.exception("Ошибка обработки вступления")

    # --- личные сообщения авторам ---

    def queue_manual_dm(self, user_id: int | None, username: str | None, tpl_id: int, title: str) -> int:
        self.dm_queue.put_nowait(DmTask(user_id, username, tpl_id, None, 0, manual=True, title=title))
        return self.dm_queue.qsize()

    async def _dm_worker(self) -> None:
        while True:
            task = await self.dm_queue.get()
            try:
                sent = await self._send_dm(task)
            except Exception:
                log.exception("Ошибка отправки ЛС")
                sent = False
            if sent:
                await asyncio.sleep(max(3, int(self.db.get("dm_delay"))))

    async def _resolve_user(self, user_id: int | None, username: str | None):
        client = self.ub.client
        for target in (user_id, username):
            if not target:
                continue
            try:
                return await client.get_input_entity(target)
            except (ValueError, TypeError, errors.RPCError):
                continue
        return None

    async def _send_dm(self, task: DmTask) -> bool:
        if not task.manual and (self.db.get("paused") or now() < self.dm_blocked_until):
            return False
        tpl = await self.db.template(task.tpl_id)
        if not tpl:
            return False
        peer = await self._resolve_user(task.user_id, task.username)
        if peer is None:
            if task.manual:
                await self.ub.event(f"⚠️ Не удалось найти пользователя {escape(task.title)} — Telegram не даёт написать по ID без контакта.")
            return False
        user_id = utils.get_peer_id(peer)

        if not task.manual and task.cooldown_h > 0:
            last = await self.db.scalar("SELECT sent_at FROM dm_log WHERE user_id = ?", (user_id,))
            if last and last > now() - task.cooldown_h * 3600:
                return False

        for attempt in range(2):
            try:
                await self.ub.send_template(peer, tpl)
                break
            except errors.FloodWaitError as e:
                if attempt or e.seconds > 900:
                    await self.ub.event(f"⏳ FloodWait {e.seconds} с при отправке ЛС {escape(task.title)}")
                    return False
                await asyncio.sleep(e.seconds + 1)
            except errors.PeerFloodError:
                self.dm_blocked_until = now() + 3600
                await self.ub.event(
                    "🚫 Telegram ограничил отправку ЛС незнакомым (PeerFlood). "
                    "Автоматические ЛС приостановлены на 1 час."
                )
                return False
            except errors.RPCError as e:
                if task.manual:
                    await self.ub.event(f"⚠️ Не удалось написать {escape(task.title)}: {e.__class__.__name__}")
                return False

        await self.db.execute(
            "INSERT INTO dm_log(user_id, rule_id, sent_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET rule_id = excluded.rule_id, sent_at = excluded.sent_at",
            (user_id, task.rule_id, now()),
        )
        if task.manual:
            await self.ub.event(f"✉️ Сообщение отправлено: {escape(task.title)}")
        return True
