from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...db import Database
from ...userbot.client import UserBot
from ..ui import SECTIONS, btn, day_start, grid, h, kb, show

router = Router(name="menu")


def section_button(key: str, db: Database):
    title, data = SECTIONS[key]
    if key == "pause":
        title = "▶️ Запустить юзербот" if db.get("paused") else "⏸ Поставить на паузу"
    return btn(title, data)


async def main_text(db: Database, ub: UserBot) -> str:
    if ub.online:
        me = ub.me
        account = f"🟢 {h(me.first_name)}" + (f" (@{h(me.username)})" if me.username else "")
    else:
        account = "🔴 не подключён"
    mode = "⏸ на паузе" if db.get("paused") else "▶️ работает"
    groups = await db.scalar("SELECT COUNT(*) FROM groups WHERE enabled = 1")
    rules = await db.scalar("SELECT COUNT(*) FROM rules WHERE enabled = 1")
    bcs = await db.scalar("SELECT COUNT(*) FROM broadcasts WHERE enabled = 1")
    leads_today = await db.scalar("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (day_start(db),))
    return (
        "🤖 <b>Панель юзербота</b>\n\n"
        f"👤 Аккаунт: {account}\n"
        f"⚙️ Режим: {mode}\n"
        f"🛰 Групп: <b>{groups}</b>   🎯 Фильтров: <b>{rules}</b>   📣 Рассылок: <b>{bcs}</b>\n"
        f"📥 Заявок сегодня: <b>{leads_today}</b>"
    )


async def render_main(event, db: Database, ub: UserBot):
    keys = [k for k in db.get("main_menu") if k in SECTIONS]
    rows = grid([section_button(k, db) for k in keys])
    rows.append([btn("➕ Ещё", "m:more")])
    await show(event, await main_text(db, ub), kb(*rows))


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext, db: Database, ub: UserBot):
    await state.clear()
    await render_main(message, db, ub)


@router.callback_query(F.data == "m:main")
async def cb_main(call: CallbackQuery, db: Database, ub: UserBot):
    await render_main(call, db, ub)
    await call.answer()


@router.callback_query(F.data == "m:more")
async def cb_more(call: CallbackQuery, db: Database):
    main = set(db.get("main_menu"))
    keys = [k for k in SECTIONS if k not in main]
    rows = grid([section_button(k, db) for k in keys])
    rows.append([btn("🎛 Настроить меню", "x:menu")])
    rows.append([btn("« Главное меню", "m:main")])
    await show(call, "➕ <b>Ещё</b>\n\nДополнительные разделы и настройки.", kb(*rows))
    await call.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()
