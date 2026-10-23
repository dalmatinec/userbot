"""Раздел «Чаты» и универсальный выбор чатов для фильтров и рассылок."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...db import Database, now
from ...userbot.client import UserBot
from ..states import Input
from ..ui import CHAT_TYPES, PAGE, ask, back, btn, cut, drop_prompt, fmt_ts, h, kb, pager, show
from . import rules

router = Router(name="chats")

# mode -> (заголовок, подсказка, только где можно писать, несколько, куда вернуться)
MODES = {
    "rs": ("🛰 Группы фильтра", "Отметьте группы/каналы, где работает этот фильтр.", False, True, "r:v:{}"),
    "ga": ("➕ Добавить группу", "Выберите группу или канал, куда бот присылает заявки. ✅ — уже отслеживается.", False, False, "g:list:0"),
    "bt": ("🎯 Чаты для рассылки", "Отметьте группы и каналы, куда отправлять рассылку.", True, True, "b:v:{}"),
    "v": ("📋 Мои чаты", "Нажмите на чат, чтобы посмотреть подробности.", False, False, "c:menu"),
}
TYPE_FILTERS = {"all": "Все типы", "groups": "👥 Только группы", "channels": "📢 Только каналы"}

# поиск и фильтр типа — на пользователя и экран, живут в памяти
_filters: dict[tuple[int, str, int], tuple[str, str]] = {}


def _where(mode: str, query: str, ftype: str) -> tuple[str, list]:
    sql, params = ["1=1"], []
    if MODES[mode][2]:
        sql.append("can_send = 1")
    if ftype == "groups":
        sql.append("type IN ('group', 'supergroup')")
    elif ftype == "channels":
        sql.append("type = 'channel'")
    if query:
        sql.append("title LIKE ? COLLATE NOCASE")
        params.append(f"%{query}%")
    return " AND ".join(sql), params


async def _selected(db: Database, mode: str, obj: int) -> set[int]:
    if mode == "rs":
        return set(await db.rule_sources(obj))
    if mode == "bt":
        return set(await db.broadcast_targets(obj))
    if mode == "ga":
        return {r["chat_id"] for r in await db.fetchall("SELECT chat_id FROM groups")}
    return set()


async def render_picker(event, db: Database, user_id: int, mode: str, obj: int, page: int):
    title, hint, _, multi, back_to = MODES[mode]
    query, ftype = _filters.get((user_id, mode, obj), ("", "all"))
    where, params = _where(mode, query, ftype)
    total = await db.scalar(f"SELECT COUNT(*) FROM chats WHERE {where}", params)
    rows = await db.fetchall(
        f"SELECT id, title, type FROM chats WHERE {where} ORDER BY title COLLATE NOCASE LIMIT ? OFFSET ?",
        [*params, PAGE, page * PAGE],
    )
    selected = await _selected(db, mode, obj)

    buttons = []
    for c in rows:
        icon = "📢" if c["type"] == "channel" else "👥"
        mark = ("✅ " if c["id"] in selected else "▫️ ") if mode != "v" else ""
        buttons.append([btn(f"{mark}{icon} {cut(c['title'], 34)}", f"pt:{mode}:{obj}:{page}:{c['id']}")])

    text = [f"<b>{title}</b>", "", hint]
    if mode != "v":
        text.append(f"Выбрано: <b>{len(selected)}</b>")
    text.append(f"Найдено чатов: <b>{total}</b>" + (f" по запросу «{h(query)}»" if query else ""))
    if not total and not query:
        text.append("\n<i>Список пуст — нажмите «🔄 Обновить» в разделе «Чаты».</i>")

    tools = [btn("🔍 Поиск" if not query else "✖️ Сбросить поиск", f"pq:{mode}:{obj}" if not query else f"pqx:{mode}:{obj}"),
             btn(TYPE_FILTERS[ftype], f"pf:{mode}:{obj}")]
    bulk = [btn("☑️ Выбрать все", f"pall:{mode}:{obj}"), btn("◻️ Снять все", f"pnone:{mode}:{obj}")] if multi else None
    await show(event, "\n".join(text), kb(
        *buttons,
        pager(f"p:{mode}:{obj}", page, total),
        tools,
        bulk,
        back(back_to.format(obj), "✅ Готово" if multi else "« Назад"),
    ))


@router.callback_query(F.data.startswith("p:"))
async def cb_picker(call: CallbackQuery, db: Database):
    _, mode, obj, page = call.data.split(":")
    await render_picker(call, db, call.from_user.id, mode, int(obj), int(page))
    await call.answer()


@router.callback_query(F.data.startswith("pt:"))
async def cb_pick(call: CallbackQuery, db: Database, ub: UserBot):
    _, mode, obj, page, chat_id = call.data.split(":")
    obj, chat_id = int(obj), int(chat_id)
    if mode == "v":
        await render_chat(call, db, chat_id)
        return await call.answer()
    if mode == "ga":
        from . import groups

        await db.add_group(chat_id)
        await ub.monitor.reload()
        await groups.render_group(call, db, chat_id)
        return await call.answer("Группа добавлена")

    table, col = ("rule_sources", "rule_id") if mode == "rs" else ("broadcast_targets", "broadcast_id")
    exists = await db.scalar(f"SELECT 1 FROM {table} WHERE {col} = ? AND chat_id = ?", (obj, chat_id))
    if exists:
        await db.execute(f"DELETE FROM {table} WHERE {col} = ? AND chat_id = ?", (obj, chat_id))
    else:
        await db.execute(f"INSERT INTO {table}({col}, chat_id) VALUES(?, ?)", (obj, chat_id))
    if mode == "rs":
        if not exists:
            await db.add_group(chat_id)
        await ub.monitor.reload()
    await render_picker(call, db, call.from_user.id, mode, obj, int(page))
    await call.answer("Убрано" if exists else "Добавлено")


@router.callback_query(F.data.startswith("pall:") | F.data.startswith("pnone:"))
async def cb_bulk(call: CallbackQuery, db: Database, ub: UserBot):
    action, mode, obj = call.data.split(":")
    obj = int(obj)
    table, col = ("rule_sources", "rule_id") if mode == "rs" else ("broadcast_targets", "broadcast_id")
    if action == "pnone":
        await db.execute(f"DELETE FROM {table} WHERE {col} = ?", (obj,))
    else:
        query, ftype = _filters.get((call.from_user.id, mode, obj), ("", "all"))
        where, params = _where(mode, query, ftype)
        await db.execute(
            f"INSERT OR IGNORE INTO {table}({col}, chat_id) SELECT ?, id FROM chats WHERE {where}",
            [obj, *params],
        )
    if mode == "rs":
        await db.execute(
            "INSERT OR IGNORE INTO groups(chat_id, added_at) SELECT chat_id, ? FROM rule_sources WHERE rule_id = ?",
            (now(), obj),
        )
        await ub.monitor.reload()
    await render_picker(call, db, call.from_user.id, mode, obj, 0)
    await call.answer("Готово")


@router.callback_query(F.data.startswith("pf:"))
async def cb_type_filter(call: CallbackQuery, db: Database):
    _, mode, obj = call.data.split(":")
    key = (call.from_user.id, mode, int(obj))
    query, ftype = _filters.get(key, ("", "all"))
    order = list(TYPE_FILTERS)
    _filters[key] = (query, order[(order.index(ftype) + 1) % len(order)])
    await render_picker(call, db, call.from_user.id, mode, int(obj), 0)
    await call.answer()


@router.callback_query(F.data.startswith("pqx:"))
async def cb_query_clear(call: CallbackQuery, db: Database):
    _, mode, obj = call.data.split(":")
    key = (call.from_user.id, mode, int(obj))
    _filters[key] = ("", _filters.get(key, ("", "all"))[1])
    await render_picker(call, db, call.from_user.id, mode, int(obj), 0)
    await call.answer()


@router.callback_query(F.data.startswith("pq:"))
async def cb_query(call: CallbackQuery, state: FSMContext):
    _, mode, obj = call.data.split(":")
    prompt = await ask(call, "🔍 Напишите часть названия чата:", f"p:{mode}:{obj}:0")
    await state.set_state(Input.picker_query)
    await state.update_data(prompt=prompt.message_id, mode=mode, obj=int(obj))
    await call.answer()


@router.message(Input.picker_query, F.text)
async def in_query(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    key = (message.from_user.id, data["mode"], data["obj"])
    _filters[key] = (message.text.strip()[:50], _filters.get(key, ("", "all"))[1])
    await render_picker(message, db, message.from_user.id, data["mode"], data["obj"], 0)


# --- раздел «Чаты» ---

async def render_menu(event, db: Database):
    stats = {r["type"]: (r["n"], r["w"]) for r in await db.fetchall(
        "SELECT type, COUNT(*) AS n, SUM(can_send) AS w FROM chats GROUP BY type"
    )}
    updated = await db.scalar("SELECT MAX(updated_at) FROM chats")

    lines = ["💬 <b>Чаты аккаунта</b>", ""]
    for key, label in CHAT_TYPES.items():
        n, w = stats.get(key, (0, 0))
        lines.append(f"{label.capitalize()}: <b>{n}</b> (можно писать: {w or 0})")
    lines += ["", f"Обновлено: {fmt_ts(updated, db)}",
              "<i>Список берётся из диалогов юзербота. Вступили в новый чат — нажмите «Обновить».</i>"]
    await show(event, "\n".join(lines), kb(
        [btn("🔄 Обновить из Telegram", "c:sync")],
        [btn("📋 Список чатов", "p:v:0:0")],
        back("m:main", "« Главное меню"),
    ))


async def render_chat(event, db: Database, chat_id: int):
    c = await db.fetchone("SELECT * FROM chats WHERE id = ?", (chat_id,))
    if not c:
        return await render_menu(event, db)
    in_rules = await db.fetchall(
        "SELECT r.name FROM rule_sources s JOIN rules r ON r.id = s.rule_id WHERE s.chat_id = ?", (chat_id,)
    )
    in_bcs = await db.fetchall(
        "SELECT b.name FROM broadcast_targets t JOIN broadcasts b ON b.id = t.broadcast_id WHERE t.chat_id = ?",
        (chat_id,),
    )
    lines = [
        f"<b>{h(c['title'])}</b>",
        "",
        f"Тип: {CHAT_TYPES.get(c['type'], c['type'])}",
        f"ID: <code>{c['id']}</code>",
        f"Ссылка: @{h(c['username'])}" if c["username"] else "Ссылка: приватный",
        f"Можно писать: {'✅ да' if c['can_send'] else '🚫 нет'}",
        f"Источник для фильтров: {h(', '.join(r['name'] for r in in_rules)) or '—'}",
        f"В рассылках: {h(', '.join(b['name'] for b in in_bcs)) or '—'}",
    ]
    await show(event, "\n".join(lines), kb(back("p:v:0:0")))


@router.callback_query(F.data == "c:menu")
async def cb_menu(call: CallbackQuery, db: Database):
    await render_menu(call, db)
    await call.answer()


@router.callback_query(F.data == "c:sync")
async def cb_sync(call: CallbackQuery, db: Database, ub: UserBot):
    if not ub.online:
        return await call.answer("Юзербот не подключён", show_alert=True)
    await call.answer("Обновляю список…")
    await ub.refresh_dialogs()
    await render_menu(call, db)
