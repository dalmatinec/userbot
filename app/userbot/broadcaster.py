"""Рассылки заготовленных сообщений по группам и каналам по расписанию."""
import asyncio
import logging
import random
import time
from html import escape

from telethon import errors

from ..db import now

log = logging.getLogger(__name__)

TICK = 15  # как часто проверять расписание, секунд

# ошибки «писать сюда нельзя» — чат помечается как недоступный для рассылки
WRITE_FORBIDDEN = (
    errors.ChatWriteForbiddenError,
    errors.ChatAdminRequiredError,
    errors.UserBannedInChannelError,
    errors.ChannelPrivateError,
    errors.ChatRestrictedError,
    errors.ChatSendMediaForbiddenError,
    errors.ChatSendPhotosForbiddenError,
    errors.ChatSendVideosForbiddenError,
    errors.ChatGuestSendForbiddenError,
)


def in_quiet_hours(spec: str, tz_offset: int) -> bool:
    """spec вида "23-8": с 23:00 до 08:00 по местному времени рассылки не идут."""
    if not spec or "-" not in spec:
        return False
    try:
        start, end = (int(x) % 24 for x in spec.split("-", 1))
    except ValueError:
        return False
    hour = (time.gmtime().tm_hour + tz_offset) % 24
    if start == end:
        return False
    return start <= hour < end if start < end else hour >= start or hour < end


class Broadcaster:
    def __init__(self, ub):
        self.ub = ub
        self.db = ub.db
        self.running: dict[int, asyncio.Task] = {}
        self.progress: dict[int, tuple[int, int]] = {}  # id -> (сделано, всего)
        self._stop: set[int] = set()
        # рассылки идут по очереди: одна сессия — один поток отправки, так меньше риск флуда
        self._lock = asyncio.Lock()

    def is_running(self, bid: int) -> bool:
        return bid in self.running

    def start(self, bid: int) -> bool:
        if bid in self.running:
            return False
        self._stop.discard(bid)
        task = self.ub.spawn(self._run(bid))
        self.running[bid] = task
        task.add_done_callback(lambda _: (self.running.pop(bid, None), self.progress.pop(bid, None)))
        return True

    def stop(self, bid: int) -> None:
        self._stop.add(bid)

    async def loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                log.exception("Ошибка планировщика рассылок")
            await asyncio.sleep(TICK)

    async def _tick(self) -> None:
        if self.db.get("paused"):
            return
        if in_quiet_hours(self.db.get("quiet_hours"), int(self.db.get("tz_offset"))):
            return
        ts = now()
        due = await self.db.fetchall(
            "SELECT id, interval_min FROM broadcasts "
            "WHERE enabled = 1 AND next_run_at <= ? AND interval_min > 0",
            (ts,),
        )
        for row in due:
            if row["id"] in self.running:
                continue
            await self.db.execute(
                "UPDATE broadcasts SET next_run_at = ? WHERE id = ?",
                (ts + row["interval_min"] * 60, row["id"]),
            )
            self.start(row["id"])

    async def _run(self, bid: int) -> None:
        async with self._lock:
            bc = await self.db.broadcast(bid)
            if not bc:
                return
            tpl_ids = await self.db.broadcast_template_ids(bid)
            targets = await self.db.broadcast_targets(bid)
            templates = [t for t in [await self.db.template(i) for i in tpl_ids] if t]
            if not templates or not targets:
                await self.ub.event(f"⚠️ Рассылка «{escape(bc['name'])}»: не выбраны шаблоны или чаты.")
                return

            media_cache: dict[int, object] = {}
            logs: list[tuple] = []
            ok = fail = 0
            rotate = bc["rotate_idx"]
            delay = max(3, bc["delay_sec"])
            self.progress[bid] = (0, len(targets))

            for i, chat_id in enumerate(targets):
                if bid in self._stop or self.db.get("paused"):
                    break
                tpl = templates[(rotate + i) % len(templates)]
                error = await self._send_one(chat_id, tpl, media_cache)
                if error is None:
                    ok += 1
                else:
                    fail += 1
                logs.append((bid, chat_id, int(error is None), error, now()))
                self.progress[bid] = (i + 1, len(targets))
                if i + 1 < len(targets):
                    await asyncio.sleep(delay * random.uniform(0.8, 1.25))

            await self.db.executemany(
                "INSERT INTO send_log(broadcast_id, chat_id, ok, error, created_at) VALUES(?,?,?,?,?)",
                logs,
            )
            await self.db.execute(
                "UPDATE broadcasts SET last_run_at = ?, last_ok = ?, last_fail = ?, rotate_idx = ? WHERE id = ?",
                (now(), ok, fail, (rotate + 1) % 1_000_000, bid),
            )
            stopped = " (остановлена)" if bid in self._stop else ""
            self._stop.discard(bid)
            await self.ub.event(
                f"📣 Рассылка «{escape(bc['name'])}» завершена{stopped}\n"
                f"✅ Успешно: <b>{ok}</b>   ❌ Ошибок: <b>{fail}</b>"
            )

    async def _send_one(self, chat_id: int, tpl, media_cache: dict) -> str | None:
        for attempt in range(2):
            try:
                msg = await self.ub.send_template(chat_id, tpl, media=media_cache.get(tpl["id"]))
                if tpl["media_path"] and msg.media and tpl["id"] not in media_cache:
                    media_cache[tpl["id"]] = msg.media  # дальше отправляем без повторной загрузки
                return None
            except errors.FloodWaitError as e:
                if attempt or e.seconds > 900:
                    return f"FloodWait {e.seconds}s"
                await asyncio.sleep(e.seconds + 1)
            except errors.SlowModeWaitError as e:
                return f"Медленный режим {e.seconds}s"
            except WRITE_FORBIDDEN as e:
                await self.db.execute("UPDATE chats SET can_send = 0 WHERE id = ?", (chat_id,))
                return e.__class__.__name__
            except (ValueError, errors.RPCError) as e:
                return e.__class__.__name__
            except OSError as e:
                return f"Файл: {e}"
        return "unknown"
