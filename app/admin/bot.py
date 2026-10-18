"""Сборка бота-админки: доступ только для админов, уведомления о заявках и событиях."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject

from ..config import Config
from ..db import Database
from ..userbot.client import UserBot
from .access import Access
from .handlers import build_router
from .handlers.leads import lead_card

log = logging.getLogger(__name__)


class AdminOnly(BaseMiddleware):
    """Пускает только админов и только в личке. Нажатие любой кнопки отменяет незавершённый ввод."""

    def __init__(self, access: Access):
        self.access = access

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]], event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if not user or not self.access.allowed(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("Нет доступа", show_alert=True)
            return None
        if isinstance(event, Message) and event.chat.type != "private":
            return None
        if isinstance(event, CallbackQuery) and (state := data.get("state")):
            await state.clear()
        return await handler(event, data)


class Notifier:
    def __init__(self, bot: Bot, access: Access, db: Database):
        self.bot = bot
        self.access = access
        self.db = db

    async def _broadcast(self, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
        for uid in self.access.all:
            try:
                await self.bot.send_message(uid, text, reply_markup=markup, disable_web_page_preview=True)
            except TelegramAPIError as e:
                log.debug("Админ %s недоступен: %s", uid, e)

    async def event(self, text: str) -> None:
        await self._broadcast(text)

    async def lead(self, lead_id: int) -> None:
        card = await lead_card(self.db, lead_id, for_notify=True)
        if card:
            await self._broadcast(*card)


def build_bot(cfg: Config, db: Database, ub: UserBot, access: Access) -> tuple[Bot, Dispatcher]:
    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    guard = AdminOnly(access)
    dp.message.outer_middleware(guard)
    dp.callback_query.outer_middleware(guard)
    dp.include_router(build_router())
    # зависимости, которые получают обработчики по имени аргумента
    dp["db"] = db
    dp["ub"] = ub
    dp["cfg"] = cfg
    dp["access"] = access
    return bot, dp


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command="menu", description="Открыть панель")])
