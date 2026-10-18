from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...db import Database, now
from ...userbot.client import UserBot
from ..states import Input
from ..ui import PAGE, ask, back, btn, cut, drop_prompt, fmt_minutes, fmt_ts, grid, h, kb, on_off, pager, show

router = Router(name="broadcasts")

INTERVALS = [(0, "Разово"), (30, "30 мин"), (60, "1 ч"), (120, "2 ч"), (180, "3 ч"),
             (360, "6 ч"), (720, "12 ч"), (1440, "24 ч")]
DELAYS = [5, 10, 15, 30, 60, 120, 300]


def bid_of(call: CallbackQuery) -> int:
    return int(call.data.split(":")[2])


async def render_list(event, db: Database, ub: UserBot, page: int = 0):
    total = await db.scalar("SELECT COUNT(*) FROM broadcasts")
    rows = await db.fetchall(
        "SELECT id, name, enabled FROM broadcasts ORDER BY id LIMIT ? OFFSET ?", (PAGE, page * PAGE)
    )
    buttons = [
        [btn(f"{'⏳' if ub.broadcaster.is_running(b['id']) else on_off(b['enabled'])} {cut(b['name'], 32)}",
             f"b:v:{b['id']}")]
        for b in rows
    ]
    await show(event, (
        "📣 <b>Рассылки</b>\n\n"
        "Отправка заготовленных сообщений в группы и каналы, где у аккаунта есть доступ: "
        "вручную или по расписанию.\n\n"
        f"Всего рассылок: <b>{total}</b>"
    ), kb(*buttons, pager("b:list", page, total), [btn("➕ Новая рассылка", "b:new")], back("m:main", "« Главное меню")))


async def render_broadcast(event, db: Database, bid: int, ub: UserBot):
    b = await db.broadcast(bid)
    if not b:
        return await show(event, "Рассылка не найдена", kb(back("b:list:0")))
    tpl_ids = await db.broadcast_template_ids(bid)
    names = [t["name"] for t in await db.fetchall(
        f"SELECT name FROM templates WHERE id IN ({','.join('?' * len(tpl_ids))})", tpl_ids
    )] if tpl_ids else []
    targets = await db.scalar("SELECT COUNT(*) FROM broadcast_targets WHERE broadcast_id = ?", (bid,))
    running = ub.broadcaster.is_running(bid)

    if running:
        done, total = ub.broadcaster.progress.get(bid, (0, targets))
        status = f"⏳ идёт отправка: {done}/{total}" if total else "⏳ в очереди"
    else:
        status = f"{on_off(b['enabled'])} {'по расписанию' if b['enabled'] else 'выключена'}"
    lines = [
        f"📣 <b>{h(b['name'])}</b>",
        "",
        f"Статус: {status}",
        f"📝 Шаблоны: {h(', '.join(names)) if names else '<i>не выбраны</i>'}"
        + (" (чередуются)" if len(names) > 1 else ""),
        f"🎯 Чатов: <b>{targets}</b>",
        f"🔁 Повтор: {fmt_minutes(b['interval_min'])}",
        f"⏳ Пауза между чатами: ~{b['delay_sec']} с",
    ]
    if b["enabled"] and b["interval_min"]:
        lines.append(f"🕒 Следующий запуск: {fmt_ts(max(b['next_run_at'], now()), db)}")
    if b["last_run_at"]:
        lines.append(f"📊 Последний запуск: {fmt_ts(b['last_run_at'], db)} — ✅ {b['last_ok']} / ❌ {b['last_fail']}")
    if db.get("quiet_hours"):
        lines.append(f"🌙 Тихие часы: {h(db.get('quiet_hours'))}")

    run_row = [btn("⏹ Остановить", f"b:stop:{bid}")] if running else [btn("▶️ Запустить сейчас", f"b:run:{bid}")]
    toggle = btn("🔴 Выключить расписание" if b["enabled"] else "🟢 Включить расписание", f"b:on:{bid}")
    await show(event, "\n".join(lines), kb(
        run_row,
        [toggle] if b["interval_min"] else None,
        [btn(f"📝 Шаблоны ({len(tpl_ids)})", f"tp:bt:{bid}:0"), btn(f"🎯 Чаты ({targets})", f"p:bt:{bid}:0")],
        [btn("🔁 Повтор", f"b:int:{bid}"), btn("⏳ Пауза", f"b:dl:{bid}")],
        [btn("📊 Отчёт", f"b:rep:{bid}"), btn("✏️ Название", f"b:ren:{bid}")],
        [btn("🗑 Удалить", f"b:del:{bid}"), btn("« К рассылкам", "b:list:0")],
    ))


@router.callback_query(F.data.startswith("b:list:"))
async def cb_list(call: CallbackQuery, db: Database, ub: UserBot):
    await render_list(call, db, ub, int(call.data.split(":")[2]))
    await call.answer()


@router.callback_query(F.data.startswith("b:v:"))
async def cb_view(call: CallbackQuery, db: Database, ub: UserBot):
    await render_broadcast(call, db, bid_of(call), ub)
    await call.answer()


@router.callback_query(F.data == "b:new")
async def cb_new(call: CallbackQuery, state: FSMContext):
    prompt = await ask(call, "➕ <b>Новая рассылка</b>\n\nНапишите название, например: <i>Утренний пост</i>", "b:list:0")
    await state.set_state(Input.bc_name)
    await state.update_data(prompt=prompt.message_id)
    await call.answer()


@router.message(Input.bc_name, F.text)
async def in_name(message: Message, state: FSMContext, db: Database, ub: UserBot):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    bid = await db.execute("INSERT INTO broadcasts(name, created_at) VALUES(?, ?)", (message.text.strip()[:64], now()))
    await render_broadcast(message, db, bid, ub)


async def _ready(db: Database, bid: int) -> str | None:
    if not await db.broadcast_template_ids(bid):
        return "Сначала выберите шаблоны 📝"
    if not await db.broadcast_targets(bid):
        return "Сначала выберите чаты 🎯"
    return None


@router.callback_query(F.data.startswith("b:on:"))
async def cb_toggle(call: CallbackQuery, db: Database, ub: UserBot):
    bid = bid_of(call)
    b = await db.broadcast(bid)
    if not b["enabled"] and (error := await _ready(db, bid)):
        return await call.answer(error, show_alert=True)
    # при включении первый запуск — в ближайшую минуту
    await db.execute("UPDATE broadcasts SET enabled = ?, next_run_at = ? WHERE id = ?",
                     (0 if b["enabled"] else 1, now(), bid))
    await render_broadcast(call, db, bid, ub)
    await call.answer("Расписание выключено" if b["enabled"] else "Расписание включено")


@router.callback_query(F.data.startswith("b:run:"))
async def cb_run(call: CallbackQuery, db: Database, ub: UserBot):
    bid = bid_of(call)
    if not ub.online:
        return await call.answer("Юзербот не подключён", show_alert=True)
    if error := await _ready(db, bid):
        return await call.answer(error, show_alert=True)
    started = ub.broadcaster.start(bid)
    await render_broadcast(call, db, bid, ub)
    await call.answer("Рассылка запущена 🚀" if started else "Уже идёт")


@router.callback_query(F.data.startswith("b:stop:"))
async def cb_stop(call: CallbackQuery, db: Database, ub: UserBot):
    ub.broadcaster.stop(bid_of(call))
    await call.answer("Остановлю после текущего чата", show_alert=True)


@router.callback_query(F.data.startswith("b:int:"))
async def cb_interval(call: CallbackQuery, db: Database):
    bid = bid_of(call)
    b = await db.broadcast(bid)
    buttons = [btn(("✅ " if b["interval_min"] == m else "") + label, f"b:seti:{bid}:{m}") for m, label in INTERVALS]
    await show(call, f"🔁 <b>Как часто повторять</b>\n\nСейчас: {fmt_minutes(b['interval_min'])}", kb(
        *grid(buttons, 4), [btn("✍️ Своё значение (мин)", f"b:inti:{bid}")], back(f"b:v:{bid}")
    ))
    await call.answer()


@router.callback_query(F.data.startswith("b:seti:"))
async def cb_set_interval(call: CallbackQuery, db: Database, ub: UserBot):
    _, _, bid, minutes = call.data.split(":")
    await _save_interval(db, int(bid), int(minutes))
    await render_broadcast(call, db, int(bid), ub)
    await call.answer("Сохранено")


async def _save_interval(db: Database, bid: int, minutes: int) -> None:
    await db.execute(
        "UPDATE broadcasts SET interval_min = ?, enabled = CASE WHEN ? = 0 THEN 0 ELSE enabled END, "
        "next_run_at = CASE WHEN last_run_at IS NULL THEN ? ELSE last_run_at + ? * 60 END WHERE id = ?",
        (minutes, minutes, now(), minutes, bid),
    )


@router.callback_query(F.data.startswith("b:inti:"))
async def cb_interval_input(call: CallbackQuery, state: FSMContext):
    bid = bid_of(call)
    prompt = await ask(call, "🔁 Отправьте интервал в минутах (минимум 5, 0 — только вручную):", f"b:v:{bid}")
    await state.set_state(Input.bc_interval)
    await state.update_data(prompt=prompt.message_id, bid=bid)
    await call.answer()


@router.message(Input.bc_interval, F.text)
async def in_interval(message: Message, state: FSMContext, db: Database, ub: UserBot):
    value = message.text.strip()
    if not value.isdigit() or 0 < int(value) < 5:
        return await message.answer("Нужно целое число минут: 0 или от 5")
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await _save_interval(db, data["bid"], min(int(value), 43200))
    await render_broadcast(message, db, data["bid"], ub)


@router.callback_query(F.data.startswith("b:dl:"))
async def cb_delay(call: CallbackQuery, db: Database):
    bid = bid_of(call)
    b = await db.broadcast(bid)
    buttons = [btn(("✅ " if b["delay_sec"] == s else "") + f"{s} с", f"b:setd:{bid}:{s}") for s in DELAYS]
    await show(call, (
        "⏳ <b>Пауза между чатами</b>\n\n"
        "Чем больше пауза, тем меньше риск ограничений от Telegram. "
        "Пауза немного случайно меняется (±20%), чтобы отправка выглядела естественно.\n\n"
        f"Сейчас: {b['delay_sec']} с"
    ), kb(*grid(buttons, 4), [btn("✍️ Своё значение (сек)", f"b:dli:{bid}")], back(f"b:v:{bid}")))
    await call.answer()


@router.callback_query(F.data.startswith("b:setd:"))
async def cb_set_delay(call: CallbackQuery, db: Database, ub: UserBot):
    _, _, bid, sec = call.data.split(":")
    await db.execute("UPDATE broadcasts SET delay_sec = ? WHERE id = ?", (int(sec), int(bid)))
    await render_broadcast(call, db, int(bid), ub)
    await call.answer("Сохранено")


@router.callback_query(F.data.startswith("b:dli:"))
async def cb_delay_input(call: CallbackQuery, state: FSMContext):
    bid = bid_of(call)
    prompt = await ask(call, "⏳ Отправьте паузу в секундах (от 3 до 3600):", f"b:v:{bid}")
    await state.set_state(Input.bc_delay)
    await state.update_data(prompt=prompt.message_id, bid=bid)
    await call.answer()


@router.message(Input.bc_delay, F.text)
async def in_delay(message: Message, state: FSMContext, db: Database, ub: UserBot):
    value = message.text.strip()
    if not value.isdigit() or not 3 <= int(value) <= 3600:
        return await message.answer("Нужно целое число от 3 до 3600")
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute("UPDATE broadcasts SET delay_sec = ? WHERE id = ?", (int(value), data["bid"]))
    await render_broadcast(message, db, data["bid"], ub)


@router.callback_query(F.data.startswith("b:rep:"))
async def cb_report(call: CallbackQuery, db: Database):
    bid = bid_of(call)
    b = await db.broadcast(bid)
    rows = await db.fetchall(
        "SELECT l.chat_id, l.error, l.created_at, c.title FROM send_log l LEFT JOIN chats c ON c.id = l.chat_id "
        "WHERE l.broadcast_id = ? AND l.ok = 0 ORDER BY l.id DESC LIMIT 15",
        (bid,),
    )
    week = await db.fetchone(
        "SELECT SUM(ok) AS ok, SUM(1 - ok) AS fail FROM send_log WHERE broadcast_id = ? AND created_at >= ?",
        (bid, now() - 7 * 86400),
    )
    lines = [f"📊 <b>Отчёт: {h(b['name'])}</b>", "",
             f"За 7 дней: ✅ {week['ok'] or 0}   ❌ {week['fail'] or 0}", ""]
    if rows:
        lines.append("<b>Последние ошибки:</b>")
        for r in rows:
            lines.append(f"• {fmt_ts(r['created_at'], db)} — {h(cut(r['title'] or str(r['chat_id']), 28))}: "
                         f"<code>{h(r['error'])}</code>")
        lines += ["", "<i>Чаты, куда писать нельзя, автоматически помечаются и пропадают из выбора.</i>"]
    else:
        lines.append("Ошибок нет 👌")
    await show(call, "\n".join(lines), kb(back(f"b:v:{bid}")))
    await call.answer()


@router.callback_query(F.data.startswith("b:ren:"))
async def cb_rename(call: CallbackQuery, state: FSMContext):
    bid = bid_of(call)
    prompt = await ask(call, "✏️ Новое название рассылки:", f"b:v:{bid}")
    await state.set_state(Input.bc_rename)
    await state.update_data(prompt=prompt.message_id, bid=bid)
    await call.answer()


@router.message(Input.bc_rename, F.text)
async def in_rename(message: Message, state: FSMContext, db: Database, ub: UserBot):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute("UPDATE broadcasts SET name = ? WHERE id = ?", (message.text.strip()[:64], data["bid"]))
    await render_broadcast(message, db, data["bid"], ub)


@router.callback_query(F.data.startswith("b:del:"))
async def cb_delete(call: CallbackQuery, db: Database):
    b = await db.broadcast(bid_of(call))
    await show(call, f"🗑 Удалить рассылку <b>{h(b['name'])}</b>?", kb(
        [btn("✅ Да, удалить", f"b:delok:{b['id']}"), btn("✖️ Отмена", f"b:v:{b['id']}")]
    ))
    await call.answer()


@router.callback_query(F.data.startswith("b:delok:"))
async def cb_delete_ok(call: CallbackQuery, db: Database, ub: UserBot):
    bid = bid_of(call)
    ub.broadcaster.stop(bid)
    await db.execute("DELETE FROM broadcasts WHERE id = ?", (bid,))
    await render_list(call, db, ub)
    await call.answer("Рассылка удалена")
