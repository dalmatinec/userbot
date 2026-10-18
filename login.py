"""Создание ОТДЕЛЬНОЙ сессии для этого юзербота.

Запуск:  python login.py            — вход по номеру и коду
         python login.py --qr       — вход по QR-коду (без кода): сканировать в Telegram на телефоне
         python login.py --string   — вывести строковую сессию для SESSION= в .env (можно вместе с --qr)

Одну и ту же сессию нельзя использовать в двух программах одновременно — Telegram
сбросит её (AUTH_KEY_DUPLICATED). Поэтому для второго юзербота на том же аккаунте
создаётся новая авторизация с теми же API_ID/API_HASH. Первый бот продолжит работать.
"""
import asyncio
import getpass
import sys

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl import types

from app.config import load_config

CODE_WHERE = {
    types.auth.SentCodeTypeApp: "в приложение Telegram — чат «Telegram» с синей галочкой (не SMS!)",
    types.auth.SentCodeTypeSms: "по SMS",
    types.auth.SentCodeTypeCall: "звонком (код продиктуют)",
    types.auth.SentCodeTypeFlashCall: "сбросом звонка (код — последние цифры номера)",
    types.auth.SentCodeTypeMissedCall: "пропущенным звонком (код — последние цифры номера)",
    types.auth.SentCodeTypeFragmentSms: "через Fragment",
    types.auth.SentCodeTypeEmailCode: "на почту, привязанную к аккаунту",
}


async def ask_password(client: TelegramClient) -> None:
    while True:
        pwd = getpass.getpass("Пароль двухэтапной защиты (облачный пароль): ")
        try:
            await client.sign_in(password=pwd)
            return
        except errors.PasswordHashInvalidError:
            print("❌ Неверный пароль, попробуйте ещё раз.")


async def login_qr(client: TelegramClient) -> None:
    print("\nНа телефоне: Telegram → Настройки → Устройства → «Подключить устройство» и отсканируйте QR.\n")
    while True:
        qr = await client.qr_login()
        try:
            import qrcode

            code = qrcode.QRCode(border=1)
            code.add_data(qr.url)
            code.print_ascii(invert=True)
        except ImportError:
            print("Установите qrcode (pip install qrcode), чтобы видеть QR в терминале. Ссылка:", qr.url)
        try:
            await qr.wait(timeout=60)
            return
        except asyncio.TimeoutError:
            print("QR устарел, показываю новый…\n")
        except errors.SessionPasswordNeededError:
            await ask_password(client)
            return


async def login_code(client: TelegramClient) -> None:
    phone = input("Номер телефона в международном формате (+7...): ").strip().replace(" ", "")
    sent = await client.send_code_request(phone)
    while True:
        where = CODE_WHERE.get(type(sent.type), type(sent.type).__name__)
        print(f"\n📨 Код отправлен {where}.")
        print("   Не пересылайте код никому и никуда — Telegram заблокирует такой вход.")
        code = input("Введите код (или пустой Enter — запросить другим способом): ").strip()
        if not code:
            try:
                sent = await client.send_code_request(phone, force_sms=True)
            except errors.RPCError as e:
                print(f"Не удалось запросить повторно: {e}. Попробуйте вход по QR: python login.py --qr")
            continue
        try:
            await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
            return
        except errors.SessionPasswordNeededError:
            await ask_password(client)
            return
        except errors.PhoneCodeInvalidError:
            print("❌ Неверный код.")
        except errors.PhoneCodeExpiredError:
            print("⌛ Код истёк, запрашиваю новый…")
            sent = await client.send_code_request(phone)


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
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Эта сессия уже авторизована — повторный вход не нужен.")
        elif "--qr" in sys.argv:
            await login_qr(client)
        else:
            await login_code(client)
    except errors.FloodWaitError as e:
        raise SystemExit(f"Telegram просит подождать {e.seconds} сек перед новой попыткой входа.") from None

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
