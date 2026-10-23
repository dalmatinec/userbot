"""Отслеживаемые группы: всё настраивается на одном экране группы.

Слова, команды, вступление, шаблоны и задержка. Внутри скрытые фильтры с именами «__…»:
по одному «ключевые слова + команды» и одному «вступление» на группу. В списке фильтров их нет.
"""
import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...db import Database, now
from ...userbot.client import UserBot
from ...userbot.matcher import split_terms
from ..states import Input
from ..ui import CHAT_TYPES, PAGE, ask, back, btn, cut, day_start, drop_prompt, fmt_delay, grid, h, kb, on_off, pager, show

router = Router(name="groups")

DELAYS = [0, 10, 20, 30, 40, 50, 60]
KW_NAME = "__kw:{}"
JOIN_NAME = "__join:{}"


def chat_of(call: CallbackQuery) -> int:
    return int(call.data.split(":")[2])


async def auto_rule(db: Database, chat_id: int, kind: str) -> int:
    """id скрытого фильтра группы. Создаёт его, если ещё нет."""
    name = (KW_NAME if kind == "kw" else JOIN_NAME).format(chat_id)
    row = await db.fetchone("SELECT id FROM rules WHERE name = ?", (name,))
    if row:
        return row["id"]
    trigger = "keywords" if kind == "kw" else "joined"
    rid = await db.execute(
        "INSERT INTO rules(name, trigger, enabled, created_at) VALUES(?, ?, 0, ?)", (name, trigger, now()),
    )
    await db.execute("INSERT OR IGNORE INTO rule_sources(rule_id, chat_id) VALUES(?, ?)", (rid, chat_id))
    return rid


async def save_kw(db: Database, chat_id: int, keywords: list[str] | None = None, commands: list[str] | None = None) -> None:
    """Сохраняет слова (одной строкой: любое из них) и/или команды. None — не менять."""
    rid = await auto_rule(db, chat_id, "kw")
    r = await db.rule(rid)
    kw = json.loads(r["keywords"]) if keywords is None else ([keywords] if keywords else [])
    cmd = json.loads(r["commands"]) if commands is None else commands
    enabled = 1 if (kw or cmd) else 0
    await db.execute(
        "UPDATE rules SET keywords = ?, commands = ?, enabled = ? WHERE id = ?",
        (json.dumps(kw, ensure_ascii=False), json.dumps(cmd, ensure_ascii=False), enabled, rid),
    )


async def render_list(event, db: Database, page: int = 0):
    total = await db.scalar("SELECT COUNT(*) FROM groups")
    rows = await db.fetchall(
        "SELECT g.chat_id, g.enabled, g.delay_sec, c.title FROM groups g LEFT JOIN chats c ON c.id = g.chat_id "
        "ORDER BY g.added_at LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    buttons = [
        [btn(f"{on_off(g['enabled'])} {cut(g['title'] or str(g['chat_id']), 30)} · ⏳{fmt_delay(g['delay_sec'])}",
             f"g:v:{g['chat_id']}")]
        for g in rows
    ]
    await show(event, (
        "🛰 <b>Отслеживаемые группы</b>\n\n"
        "В каждой группе задаёте ключевые слова, команды, приветствие новичков и шаблоны ответа. "
        "Всё на одном экране.\n\n"
        f"Групп: <b>{total}</b>"
    ), kb(*buttons, pager("g:list", page, total), [btn("➕ Добавить группу", "p:ga:0:0")],
          back("m:main", "« Главное меню")))


async def render_group(event, db: Database, chat_id: int):
    g = await db.group(chat_id)
    if not g:
        return await render_list(event, db)
    chat = await db.fetchone("SELECT title, type FROM chats WHERE id = ?", (chat_id,))
    kw = await db.rule(await auto_rule(db, chat_id, "kw"))
    jn = await db.rule(await auto_rule(db, chat_id, "join"))
    words = json.loads(kw["keywords"])
    words = words[0] if words else []
    commands = json.loads(kw["commands"])
    kw_tpl = await db.template(kw["reply_tpl"])
    dm_tpl = await db.template(kw["dm_tpl"])
    jn_tpl = await db.template(jn["reply_tpl"])
    today = await db.scalar(
        "SELECT COUNT(*) FROM leads WHERE chat_id = ? AND created_at >= ?", (chat_id, day_start(db))
    )
    title = chat["title"] if chat else str(chat_id)
    lines = [
        f"🛰 <b>{h(title)}</b>   {on_off(g['enabled'])} {'отслеживается' if g['enabled'] else 'выключена'}",
        f"{CHAT_TYPES.get(chat['type'], '') if chat else ''} · <code>{chat_id}</code>",
        f"📥 Заявок сегодня: <b>{today}</b>",
        "",
        f"🔑 Ключевые слова: {h(', '.join(words)) if words else '<i>не заданы</i>'}",
        f"⌨️ Команды: {h(', '.join(commands)) if commands else '<i>не заданы</i>'}",
        f"👋 Приветствие новичков: {'включено' if jn['enabled'] else 'выключено'}, "
        f"шаблон: {h(jn_tpl['name']) if jn_tpl else '<i>не выбран</i>'}",
        f"💬 Ответ на заявки: {h(kw_tpl['name']) if kw_tpl else 'нет'}",
        f"✉️ ЛС автору: {h(dm_tpl['name']) if dm_tpl else 'нет'}",
        f"⏳ Задержка: <b>{fmt_delay(g['delay_sec'])}</b>",
        f"🔔 Уведомления: <b>{'да' if g['notify'] else 'нет'}</b>",
    ]
    await show(event, "\n".join(lines), kb(
        [btn("🔴 Выключить группу" if g["enabled"] else "🟢 Включить группу", f"g:on:{chat_id}"),
         btn(f"⏳ Задержка: {fmt_delay(g['delay_sec'])}", f"g:dl:{chat_id}")],
        [btn("🔑 Ключевые слова", f"g:kw:{chat_id}"), btn("⌨️ Команды", f"g:cmd:{chat_id}")],
        [btn(f"👋 Приветствие: {on_off(jn['enabled'])}", f"g:jn:{chat_id}"),
         btn("🎉 Шаблон приветствия", f"tp:rr:{jn['id']}:0")],
        [btn("💬 Ответ на заявки", f"tp:rr:{kw['id']}:0"), btn("✉️ ЛС автору", f"tp:rd:{kw['id']}:0")],
        [btn("⏱ Частота ЛС", f"r:cd:{kw['id']}"), btn(f"🔔 Уведомления: {'да' if g['notify'] else 'нет'}", f"g:ntf:{chat_id}")],
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
        "Пауза перед ответом на заявку, сообщением новичку и ЛС автору. "
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


# --- ввод слов и команд ---

async def _ask_terms(call: CallbackQuery, state: FSMContext, chat_id: int, kind: str) -> None:
    if kind == "kw":
        text = ("🔑 <b>Ключевые слова группы</b>\n\n"
                "Напишите слова через запятую. Заявка подойдёт, если в ней есть хотя бы одно из них.\n\n"
                "Например: <i>Алматы, специи, Астана, 100 гр</i>")
        st = Input.grp_kw
    else:
        text = ("⌨️ <b>Команды группы</b>\n\n"
                "Напишите команды через запятую. Сообщение, которое начинается с команды, сработает.\n\n"
                "Например: <i>/start, старт, меню</i>")
        st = Input.grp_cmd
    prompt = await ask(call, text, f"g:v:{chat_id}")
    await state.set_state(st)
    await state.update_data(prompt=prompt.message_id, group=chat_id)
    await call.answer()


@router.callback_query(F.data.startswith("g:kw:"))
async def cb_kw(call: CallbackQuery, state: FSMContext):
    await _ask_terms(call, state, chat_of(call), "kw")


@router.callback_query(F.data.startswith("g:cmd:"))
async def cb_cmd(call: CallbackQuery, state: FSMContext):
    await _ask_terms(call, state, chat_of(call), "cmd")


@router.message(Input.grp_kw, F.text)
async def in_kw(message: Message, state: FSMContext, db: Database, ub: UserBot):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await save_kw(db, data["group"], keywords=split_terms(message.text))
    await ub.monitor.reload()
    await render_group(message, db, data["group"])


@router.message(Input.grp_cmd, F.text)
async def in_cmd(message: Message, state: FSMContext, db: Database, ub: UserBot):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await save_kw(db, data["group"], commands=split_terms(message.text))
    await ub.monitor.reload()
    await render_group(message, db, data["group"])


@router.callback_query(F.data.startswith("g:jn:"))
async def cb_join(call: CallbackQuery, db: Database, ub: UserBot):
    chat_id = chat_of(call)
    rid = await auto_rule(db, chat_id, "join")
    await db.execute("UPDATE rules SET enabled = 1 - enabled WHERE id = ?", (rid,))
    await ub.monitor.reload()
    await render_group(call, db, chat_id)
    await call.answer()


@router.callback_query(F.data.startswith("g:del:"))
async def cb_delete(call: CallbackQuery, db: Database):
    chat_id = chat_of(call)
    await show(call, "🗑 Перестать отслеживать эту группу?\n\n"
                     "Слова, команды и шаблоны этой группы будут удалены.", kb(
        [btn("✅ Да, убрать", f"g:delok:{chat_id}"), btn("✖️ Отмена", f"g:v:{chat_id}")]
    ))
    await call.answer()


@router.callback_query(F.data.startswith("g:delok:"))
async def cb_delete_ok(call: CallbackQuery, db: Database, ub: UserBot):
    chat_id = chat_of(call)
    await db.execute("DELETE FROM rules WHERE name IN (?, ?)", (KW_NAME.format(chat_id), JOIN_NAME.format(chat_id)))
    await db.execute("DELETE FROM rule_sources WHERE chat_id = ?", (chat_id,))
    await db.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
    await ub.monitor.reload()
    await render_list(call, db)
    await call.answer("Группа убрана")
