"""Юзербот-кубик: команда .dice [N] бросает 🎲, пока не выпадет MIN_VALUE или больше.

Неудачные броски сразу удаляются у всех. Работает только на ваших собственных
сообщениях (outgoing), в любом чате.
"""
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.types import InputMediaDice

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.getenv("SESSION", "userbot").strip() or "userbot"
DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()
MIN_VALUE = int(os.getenv("DICE_MIN", "5"))      # 5 → выпадает только 5 или 6
MAX_ROLLS = int(os.getenv("DICE_MAX_ROLLS", "10"))  # защита от .dice 1000

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logging.getLogger("telethon").setLevel(logging.WARNING)
log = logging.getLogger("dice")


def make_session():
    if len(SESSION) > 100:  # строковая сессия из .env
        return StringSession(SESSION)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(DATA_DIR / SESSION)


client = TelegramClient(
    make_session(), API_ID, API_HASH,
    device_model="Admin Userbot", system_version="1.0", app_version="1.0",
    flood_sleep_threshold=60,
)


async def lucky_roll(chat_id: int) -> int:
    while True:
        msg = await client.send_message(chat_id, file=InputMediaDice("🎲"))
        value = msg.media.value
        if value >= MIN_VALUE:
            return value
        await msg.delete()          # неудачный бросок удаляем у всех
        await asyncio.sleep(1)      # пауза от флуд-лимита


@client.on(events.NewMessage(outgoing=True, pattern=r"^\.dice(?:\s+(\d+))?$"))
async def on_dice(event):
    count = max(1, min(int(event.pattern_match.group(1) or 1), MAX_ROLLS))
    await event.delete()  # убираем саму команду
    values = []
    for i in range(count):
        try:
            values.append(await lucky_roll(event.chat_id))
        except errors.RPCError as e:
            log.warning("Не удалось бросить кубик: %r", e)
            return
        if i < count - 1:
            await asyncio.sleep(1)
    log.info("Чат %s: %s (сумма %s)", event.chat_id, values, sum(values))


async def main():
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("Сессия не авторизована — запустите: python login.py")
    me = await client.get_me()
    log.info("Юзербот запущен: %s (id %s). Команда: .dice или .dice 3", me.first_name, me.id)
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
