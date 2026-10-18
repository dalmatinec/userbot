"""Создание ОТДЕЛЬНОЙ сессии для этого юзербота.

Запуск:  python login.py            — сессия-файл data/<SESSION>.session
         python login.py --string   — вывести строковую сессию для SESSION= в .env

Одну и ту же сессию нельзя использовать в двух программах одновременно — Telegram
сбросит её (AUTH_KEY_DUPLICATED). Поэтому для второго юзербота на том же аккаунте
создаётся новая авторизация с теми же API_ID/API_HASH. Первый бот продолжит работать.
"""
import asyncio
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import load_config


async def main() -> None:
    cfg = load_config(require_bot=False)
    as_string = "--string" in sys.argv
    if as_string:
        session = StringSession()
    else:
        if len(cfg.session) > 100:
            raise SystemExit("В .env уже строковая сессия. Уберите SESSION или запустите с --string.")
        session = str(cfg.data_dir / cfg.session)

    client = TelegramClient(session, cfg.api_id, cfg.api_hash,
                            device_model="Admin Userbot", system_version="1.0", app_version="1.0")
    await client.start()  # спросит телефон, код из Telegram и пароль 2FA, если включён
    me = await client.get_me()
    print(f"\n✅ Вход выполнен: {me.first_name} (id {me.id})")
    if as_string:
        print("\nДобавьте в .env строку (никому её не показывайте):\n")
        print(f"SESSION={client.session.save()}\n")
    else:
        print(f"Сессия сохранена: {session}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
