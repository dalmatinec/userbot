"""Отслеживаемые группы: у каждой свой статус, задержка, уведомления и свои фильтры."""
import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ...db import Database
from ...userbot.client import UserBot
from ..states import Input
from ..ui import CHAT_TYPES, PAGE, TRIGGERS, ask, back, btn, cut, day_start, fmt_delay, grid, h, kb, on_off, pager, show

router = Router(name="groups")

DELAYS = [0, 10, 20, 30, 40, 50, 60]


def chat_of(call: CallbackQuery) -> int:
    return int(call.data.split(":")[2])


async def render_list(event, db: Database, page: int = 0):
    total = await db.scalar("SELECT COUNT(*) FROM groups")
    rows = await db.fetchall(
        "SELECT g.chat_id, g.enabled, g.delay_sec, c.title, "
        "(SELECT COUNT(*) FROM rule_sources s WHERE s.chat_id = g.chat_id) AS rules "
        "FROM groups g LEFT JOIN chats c ON c.id = g.chat_id "
        "ORDER BY g.added_at LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    buttons = [
        [btn(f"{on_off(g['enabled'])} {cut(g['title'] or str(g['chat_id']), 26)} · 🎯{g['rules']} · ⏳{fmt_delay(g['delay_sec'])}",
             f"g:v:{g['chat_id']}")]
        for g in rows
    ]
    await show(event, (
        "🛰 <b>Отслеживаемые группы</b>\n\n"
        "Группы и каналы, куда приходят заявки. У каждой группы свои настройки: "
        "включена или нет, задержка реакции, уведомления и свои фильтры (команды, ключевые слова).\n\n"
        f"Групп: <b>{total}</b>"
    ), kb(*buttons, pager("g:list", page, total), [btn("➕ Добавить группу", "p:ga:0:0")],
          back("m:main", "« Главное меню")))


async def render_group(event, db: Database, chat_id: int):
    g = await db.group(chat_id)
    if not g:
        return await render_list(event, db)
    chat = await db.fetchone("SELECT title, type FROM chats WHERE id = ?", (chat_id,))
    rules = await db.fetchall(
        "SELECT r.id, r.name, r.enabled, r.trigger FROM rules r "
        "JOIN rule_sources s ON s.rule_id = r.id WHERE s.chat_id = ? ORDER BY r.id",
        (chat_id,),
    )
    today = await db.scalar(
        "SELECT COUNT(*) FROM leads WHERE chat_id = ? AND created_at >= ?", (chat_id, day_start(db))
    )
    title = chat["title"] if chat else str(chat_id)
    lines = [
        f"🛰 <b>{h(title)}</b>   {on_off(g['enabled'])} {'отслеживается' if g['enabled'] else 'выключена'}",
        f"{CHAT_TYPES.get(chat['type'], '') if chat else ''} · <code>{chat_id}</code>",
        "",
        f"⏳ Задержка реакции: <b>{fmt_delay(g['delay_sec'])}</b>",
        "<i>   пауза перед ответом в группе, ЛС автору и пересылкой</i>",
        f"🔔 Уведомления из группы: <b>{'да' if g['notify'] else 'нет'}</b>",
        f"📥 Заявок сегодня: <b>{today}</b>",
        "",
        f"<b>🎯 Фильтры группы ({len(rules)}):</b>",
    ]
    if rules:
        lines += [f"{on_off(r['enabled'])} {h(r['name'])} — {TRIGGERS[r['trigger']]}" for r in rules]
    else:
        lines.append("<i>Пока нет — добавьте команды или ключевые слова кнопками ниже.</i>")

    rule_rows = [
        [btn(f"{on_off(r['enabled'])} {cut(r['name'], 28)}", f"r:v:{r['id']}"),
         btn("⏯", f"g:rt:{chat_id}:{r['id']}")]
        for r in rules
    ]
    await show(event, "\n".join(lines), kb(
        [btn("🔴 Выключить группу" if g["enabled"] else "🟢 Включить группу", f"g:on:{chat_id}")],
        [btn(f"⏳ Задержка: {fmt_delay(g['delay_sec'])}", f"g:dl:{chat_id}"),
         btn(f"🔔 Уведомления: {'да' if g['notify'] else 'нет'}", f"g:ntf:{chat_id}")],
        *rule_rows,
        [btn("➕ Команды", f"g:nr:{chat_id}:commands"), btn("➕ Ключевые слова", f"g:nr:{chat_id}:keywords")],
        [btn("➕ Любое сообщение", f"g:nr:{chat_id}:any"), btn("➕ Вступление", f"g:nr:{chat_id}:joined")],
        [btn("🗑 Убрать группу", f"g:del:{chat_id}"), btn("« К группам", "g:list:0")],
    ))


@router.callback_query(F.data.startswith("g:list:"))
async def cb_list(call: CallbackQuery, db: Database):
    await render_list(call, db, chat_of(call))
    await call.answer()


@router.callback_query(F.data.startswith("g:v:"))
async def cb_view(call: CallbackQuery, db: Database):
    await render_group(call, db, chat_of(call))
    await call.answer()


@router.callback_query(F.data.startswith("g:on:"))
async def cb_toggle(call: CallbackQuery, db: Database, ub: UserBot):
    chat_id = chat_of(call)
    g = await db.group(chat_id)
    await db.execute("UPDATE groups SET enabled = 1 - enabled WHERE chat_id = ?", (chat_id,))
    await ub.monitor.reload()
    await render_group(call, db, chat_id)
    await call.answer("Группа выключена" if g["enabled"] else "Группа включена")


@router.callback_query(F.data.startswith("g:ntf:"))
async def cb_notify(call: CallbackQuery, db: Database, ub: UserBot):
    chat_id = chat_of(call)
    await db.execute("UPDATE groups SET notify = 1 - notify WHERE chat_id = ?", (chat_id,))
    await ub.monitor.reload()
    await render_group(call, db, chat_id)
    await call.answer()


@router.callback_query(F.data.startswith("g:dl:"))
async def cb_delay(call: CallbackQuery, db: Database):
    chat_id = chat_of(call)
    g = await db.group(chat_id)
    buttons = [btn(("✅ " if g["delay_sec"] == s else "") + fmt_delay(s), f"g:setd:{chat_id}:{s}") for s in DELAYS]
    await show(call, (
        "⏳ <b>Задержка реакции</b>\n\n"
        "Сколько ждать после заявки перед ответом в группе, ЛС автору и пересылкой. "
        "Уведомление в бот приходит сразу."
    ), kb(*grid(buttons, 4), back(f"g:v:{chat_id}")))
    await call.answer()


@router.callback_query(F.data.startswith("g:setd:"))
async def cb_set_delay(call: CallbackQuery, db: Database, ub: UserBot):
    _, _, chat_id, sec = call.data.split(":")
    await db.execute("UPDATE groups SET delay_sec = ? WHERE chat_id = ?", (int(sec), int(chat_id)))
    await ub.monitor.reload()
    await render_group(call, db, int(chat_id))
    await call.answer("Сохранено")


@router.callback_query(F.data.startswith("g:rt:"))
async def cb_rule_toggle(call: CallbackQuery, db: Database, ub: UserBot):
    """Быстрое вкл/выкл фильтра прямо из экрана группы (с теми же проверками, что в карточке фильтра)."""
    _, _, chat_id, rid = call.data.split(":")
    r = await db.rule(int(rid))
    if not r["enabled"]:
        if r["trigger"] == "keywords" and not json.loads(r["keywords"]):
            return await call.answer("У фильтра нет ключевых слов — откройте его и добавьте 🔑", show_alert=True)
        if r["trigger"] == "commands" and not json.loads(r["commands"]):
            return await call.answer("У фильтра нет команд — откройте его и добавьте ⌨️", show_alert=True)
    await db.execute("UPDATE rules SET enabled = 1 - enabled WHERE id = ?", (r["id"],))
    await ub.monitor.reload()
    await render_group(call, db, int(chat_id))
    await call.answer("Фильтр выключен" if r["enabled"] else "Фильтр включён")


@router.callback_query(F.data.startswith("g:nr:"))
async def cb_new_rule(call: CallbackQuery, state: FSMContext):
    _, _, chat_id, trigger = call.data.split(":")
    examples = {"commands": "Команда /start", "keywords": "Москва + iPhone", "any": "Все сообщения",
                "joined": "Приветствие новичкам"}
    prompt = await ask(call, f"➕ <b>Новый фильтр: {TRIGGERS[trigger]}</b>\n\n"
                             f"Напишите название, например: <i>{examples[trigger]}</i>", f"g:v:{chat_id}")
    await state.set_state(Input.rule_name)
    await state.update_data(prompt=prompt.message_id, group=int(chat_id), trigger=trigger)
    await call.answer()


@router.callback_query(F.data.startswith("g:del:"))
async def cb_delete(call: CallbackQuery, db: Database):
    chat_id = chat_of(call)
    await show(call, "🗑 Перестать отслеживать эту группу?\n\n"
                     "Фильтры останутся в разделе «🎯 Фильтры», но эта группа будет убрана из них.", kb(
        [btn("✅ Да, убрать", f"g:delok:{chat_id}"), btn("✖️ Отмена", f"g:v:{chat_id}")]
    ))
    await call.answer()


@router.callback_query(F.data.startswith("g:delok:"))
async def cb_delete_ok(call: CallbackQuery, db: Database, ub: UserBot):
    chat_id = chat_of(call)
    await db.execute("DELETE FROM rule_sources WHERE chat_id = ?", (chat_id,))
    await db.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
    await ub.monitor.reload()
    await render_list(call, db)
    await call.answer("Группа убрана")
