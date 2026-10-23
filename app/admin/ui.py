"""Общие элементы интерфейса админки: клавиатуры, навигация, форматирование."""
import time
from html import escape

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..db import Database

PAGE = 8

# Разделы админки. Какие из них стоят в главном меню, а какие в «Ещё» — настраивается.
SECTIONS: dict[str, tuple[str, str]] = {
    "groups": ("🛰 Группы", "g:list:0"),
    "rules": ("🎯 Фильтры", "r:list:0"),
    "leads": ("📥 Заявки", "l:list:0"),
    "templates": ("📝 Шаблоны", "t:list:0"),
    "broadcasts": ("📣 Рассылки", "b:list:0"),
    "chats": ("💬 Чаты", "c:menu"),
    "stats": ("📊 Статистика", "x:stats"),
    "settings": ("⚙️ Настройки", "x:settings"),
    "account": ("👤 Аккаунт", "x:account"),
    "admins": ("👥 Админы", "x:admins"),
    "pause": ("⏯ Пауза / запуск", "x:pause"),
}

TRIGGERS = {
    "keywords": "🔑 Ключевые слова",
    "commands": "⌨️ Свои команды",
    "any": "📨 Любое сообщение",
    "joined": "👋 Вступление в группу",
}

CHAT_TYPES = {"group": "👥 группа", "supergroup": "👥 супергруппа", "channel": "📢 канал"}


def btn(text: str, data: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=data)


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def grid(buttons: list[InlineKeyboardButton], cols: int = 2) -> list[list[InlineKeyboardButton]]:
    return [buttons[i:i + cols] for i in range(0, len(buttons), cols)]


def back(data: str, text: str = "« Назад") -> list[InlineKeyboardButton]:
    return [btn(text, data)]


def pager(prefix: str, page: int, total: int, size: int = PAGE) -> list[InlineKeyboardButton]:
    pages = max(1, (total + size - 1) // size)
    if pages == 1:
        return []
    return [
        btn("◀️", f"{prefix}:{page - 1}") if page > 0 else btn("·", "noop"),
        btn(f"{page + 1} / {pages}", "noop"),
        btn("▶️", f"{prefix}:{page + 1}") if page < pages - 1 else btn("·", "noop"),
    ]


async def show(event: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> Message:
    """Перерисовывает текущий экран (редактирует сообщение) или присылает новый."""
    if isinstance(event, CallbackQuery):
        msg = event.message
        try:
            if msg.text:
                result = await msg.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
                return result if isinstance(result, Message) else msg
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return msg
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        return await msg.answer(text, reply_markup=markup, disable_web_page_preview=True)
    return await event.answer(text, reply_markup=markup, disable_web_page_preview=True)


async def ask(event: Message | CallbackQuery, text: str, back_to: str) -> Message:
    """Экран ввода: подсказка + кнопка отмены (любая кнопка отменяет ввод)."""
    return await show(event, text, kb(back(back_to, "✖️ Отмена")))


async def drop_prompt(message: Message, prompt_id: int | None) -> None:
    for mid in (prompt_id, message.message_id):
        if not mid:
            continue
        try:
            await message.bot.delete_message(message.chat.id, mid)
        except TelegramBadRequest:
            pass


def h(text) -> str:
    return escape(str(text or ""))


def cut(text: str, n: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def tz(db: Database) -> int:
    return int(db.get("tz_offset"))


def fmt_ts(ts: int | None, db: Database, with_date: bool = True) -> str:
    if not ts:
        return "—"
    t = time.gmtime(ts + tz(db) * 3600)
    return time.strftime("%d.%m %H:%M" if with_date else "%H:%M", t)


def day_start(db: Database, days_ago: int = 0) -> int:
    off = tz(db) * 3600
    now = int(time.time())
    return (now + off) // 86400 * 86400 - off - days_ago * 86400


def fmt_minutes(m: int) -> str:
    if m <= 0:
        return "разово (вручную)"
    if m % 1440 == 0:
        return f"каждые {m // 1440} д"
    if m % 60 == 0:
        return f"каждые {m // 60} ч"
    return f"каждые {m} мин"


def fmt_delay(sec: int) -> str:
    return f"{sec} с" if sec else "сразу"


def on_off(flag) -> str:
    return "🟢" if flag else "🔴"


def message_link(chat_id: int, msg_id: int, username: str | None) -> str | None:
    if username:
        return f"https://t.me/{username}/{msg_id}"
    s = str(chat_id)
    if s.startswith("-100"):
        return f"https://t.me/c/{s[4:]}/{msg_id}"
    return None
