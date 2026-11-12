# Юзербот-кубик 🎲

Команда в любом чате (от своего аккаунта):

- `.dice` — один бросок, всегда 5 или 6;
- `.dice 3` — три броска подряд.

Сама команда удаляется. Кубик бросается настоящий; если выпало меньше `DICE_MIN`,
сообщение сразу удаляется и бросок повторяется.

## Установка

```bash
cd /opt/userbot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # заполнить API_ID, API_HASH, SESSION
.venv/bin/python login.py   # только если сессии ещё нет
.venv/bin/python main.py
```

Сервис systemd — `deploy/userbot-admin.service`.
