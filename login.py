"""Вход в аккаунт, если сессии ещё нет (обычно не нужен — старая сессия в data/ подходит).

Запуск: python login.py
"""
from main import client


async def run():
    await client.start()
    me = await client.get_me()
    print(f"✅ Вход выполнен: {me.first_name} (id {me.id})")
    await client.disconnect()


if __name__ == "__main__":
    client.loop.run_until_complete(run())
