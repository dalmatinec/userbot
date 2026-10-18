"""Точка входа: юзербот (Telethon) и бот-админка (aiogram) в одном процессе."""
import asyncio
import contextlib
import logging

from app.admin.access import Access
from app.admin.bot import Notifier, build_bot, set_commands
from app.config import load_config
from app.db import Database
from app.userbot.client import FATAL_ERRORS, UserBot

log = logging.getLogger("main")


async def run_userbot(ub: UserBot, notifier: Notifier) -> None:
    delay = 10
    while True:
        try:
            await ub.run()
        except RuntimeError as e:  # сессия не авторизована — ждать бессмысленно
            log.error("%s", e)
            return
        except FATAL_ERRORS as e:
            log.error("Сессия юзербота недействительна: %r", e)
            await notifier.event(
                f"⛔️ Сессия юзербота недействительна (<code>{e.__class__.__name__}</code>).\n"
                "Создайте новую: <code>python login.py</code>, затем перезапустите сервис."
            )
            return
        except Exception as e:
            log.exception("Юзербот упал")
            await notifier.event(f"⚠️ Юзербот отключился: <code>{e.__class__.__name__}</code>. Переподключаюсь…")
        if ub.stopping:
            return
        await asyncio.sleep(delay)
        delay = min(delay * 2, 300)


async def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    db = Database(cfg.db_path)
    await db.connect()
    access = Access(cfg.admin_ids, await db.admin_ids())
    ub = UserBot(cfg, db)
    bot, dp = build_bot(cfg, db, ub, access)
    notifier = Notifier(bot, access, db)
    ub.on_event = notifier.event
    ub.on_lead = notifier.lead

    await set_commands(bot)
    ub_task = asyncio.create_task(run_userbot(ub, notifier))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await ub.stop()
        ub_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ub_task
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
