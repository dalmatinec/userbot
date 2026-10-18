import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...db import Database, now
from ...userbot.client import UserBot
from ...userbot.matcher import compile_rule, split_terms
from ..states import Input
from ..ui import PAGE, TRIGGERS, ask, back, btn, cut, day_start, drop_prompt, h, kb, on_off, pager, show

router = Router(name="rules")

KW_HELP = (
    "Слова через запятую — достаточно <b>любого</b> из них.\n"
    "• <code>москв</code> — найдёт «Москва», «Москве», «москвы» (поиск с начала слова)\n"
    "• <code>\"спб\"</code> — только слово целиком\n"
    "• <code>re:айфон\\s?1[3-6]</code> — регулярное выражение\n\n"
    "Каждая группа слов — отдельное условие: заявка должна подойти под <b>все</b> группы.\n"
    "Пример: группа 1 — города, группа 2 — товары ⇒ сработает на «город И товар»."
)


async def render_list(event, db: Database, page: int = 0):
    total = await db.scalar("SELECT COUNT(*) FROM rules")
    rows = await db.fetchall(
        "SELECT id, name, enabled, trigger FROM rules ORDER BY id LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    buttons = [[btn(f"{on_off(r['enabled'])} {cut(r['name'], 30)}", f"r:v:{r['id']}")] for r in rows]
    text = (
        "🎯 <b>Фильтры заявок</b>\n\n"
        "Фильтр следит за группами, куда бот пересылает заявки, и реагирует на "
        "команду /start, любое сообщение или ключевые слова (город, товар, город + товар…).\n\n"
        f"Всего фильтров: <b>{total}</b>"
    )
    await show(event, text, kb(
        *buttons,
        pager("r:list", page, total),
        [btn("➕ Новый фильтр", "r:new")],
        back("m:main", "« Главное меню"),
    ))


async def render_rule(event, db: Database, rid: int):
    r = await db.rule(rid)
    if not r:
        return await render_list(event, db)
    groups = json.loads(r["keywords"])
    exclude = json.loads(r["exclude"])
    sources = await db.rule_sources(rid)
    titles = await db.chat_titles(sources + ([r["forward_to"]] if r["forward_to"] else []))
    reply_tpl = await db.template(r["reply_tpl"])
    dm_tpl = await db.template(r["dm_tpl"])
    today = await db.scalar(
        "SELECT COUNT(*) FROM leads WHERE rule_id = ? AND created_at >= ?", (rid, day_start(db))
    )
    total = await db.scalar("SELECT COUNT(*) FROM leads WHERE rule_id = ?", (rid,))

    lines = [
        f"🎯 <b>{h(r['name'])}</b>   {on_off(r['enabled'])} {'включён' if r['enabled'] else 'выключен'}",
        "",
        f"Срабатывает на: <b>{TRIGGERS[r['trigger']]}</b>",
    ]
    if r["trigger"] == "keywords":
        if groups:
            lines.append("🔑 Условия:")
            for i, g in enumerate(groups, 1):
                prefix = "   " if i == 1 else "   <b>И</b> "
                lines.append(f"{prefix}{i}) {h(cut(', '.join(g), 120))}")
        else:
            lines.append("🔑 Условия: <i>не заданы</i>")
    if exclude:
        lines.append(f"🚫 Минус-слова: {h(cut(', '.join(exclude), 120))}")
    src_names = ", ".join(h(cut(titles.get(c, str(c)), 25)) for c in sources[:5])
    more = f" и ещё {len(sources) - 5}" if len(sources) > 5 else ""
    lines.append(f"📍 Источники: {src_names + more if sources else '<i>не выбраны</i>'}")
    lines += [
        "",
        "<b>Действия при совпадении:</b>",
        f"🔔 Уведомление в этот бот: {'да' if r['notify'] else 'нет'}",
        f"↪️ Пересылать в: {h(titles.get(r['forward_to'], r['forward_to'])) if r['forward_to'] else 'нет'}",
        f"💬 Ответ в группе: {h(reply_tpl['name']) if reply_tpl else 'нет'}",
        f"✉️ ЛС автору: {h(dm_tpl['name']) if dm_tpl else 'нет'}"
        + (f" (не чаще 1 раза в {r['cooldown_h']} ч)" if dm_tpl and r["cooldown_h"] else ""),
        "",
        f"📥 Заявок: сегодня <b>{today}</b>, всего <b>{total}</b>",
    ]

    await show(event, "\n".join(lines), kb(
        [btn("🔴 Выключить" if r["enabled"] else "🟢 Включить", f"r:on:{rid}"),
         btn("🎯 Триггер", f"r:trg:{rid}")],
        [btn("🔑 Ключевые слова", f"r:kw:{rid}"), btn("🚫 Минус-слова", f"r:ex:{rid}")],
        [btn(f"📍 Источники ({len(sources)})", f"p:rs:{rid}:0"),
         btn(f"🔔 Уведомления: {'да' if r['notify'] else 'нет'}", f"r:ntf:{rid}")],
        [btn("↪️ Пересылка", f"p:rf:{rid}:0"), btn("💬 Ответ в группе", f"tp:rr:{rid}:0")],
        [btn("✉️ ЛС автору", f"tp:rd:{rid}:0"), btn("⏱ Частота ЛС", f"r:cd:{rid}")],
        [btn("🧪 Проверить текст", f"r:test:{rid}"), btn("✏️ Название", f"r:ren:{rid}")],
        [btn("🗑 Удалить", f"r:del:{rid}"), btn("« К фильтрам", "r:list:0")],
    ))


def rid_of(call: CallbackQuery) -> int:
    return int(call.data.split(":")[2])


@router.callback_query(F.data.startswith("r:list:"))
async def cb_list(call: CallbackQuery, db: Database):
    await render_list(call, db, int(call.data.split(":")[2]))
    await call.answer()


@router.callback_query(F.data.startswith("r:v:"))
async def cb_view(call: CallbackQuery, db: Database):
    await render_rule(call, db, rid_of(call))
    await call.answer()


@router.callback_query(F.data == "r:new")
async def cb_new(call: CallbackQuery, state: FSMContext):
    prompt = await ask(call, "➕ <b>Новый фильтр</b>\n\nНапишите название, например: <i>Москва — iPhone</i>", "r:list:0")
    await state.set_state(Input.rule_name)
    await state.update_data(prompt=prompt.message_id)
    await call.answer()


@router.message(Input.rule_name, F.text)
async def in_rule_name(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    rid = await db.execute(
        "INSERT INTO rules(name, created_at) VALUES(?, ?)", (message.text.strip()[:64], now())
    )
    await render_rule(message, db, rid)


@router.callback_query(F.data.startswith("r:on:"))
async def cb_toggle(call: CallbackQuery, db: Database, ub: UserBot):
    rid = rid_of(call)
    r = await db.rule(rid)
    if not r:
        return await call.answer()
    if not r["enabled"]:
        if not await db.rule_sources(rid):
            return await call.answer("Сначала выберите группы-источники 📍", show_alert=True)
        if r["trigger"] == "keywords" and not json.loads(r["keywords"]):
            return await call.answer("Добавьте ключевые слова 🔑 или смените триггер", show_alert=True)
    await db.execute("UPDATE rules SET enabled = 1 - enabled WHERE id = ?", (rid,))
    await ub.monitor.reload()
    await render_rule(call, db, rid)
    await call.answer("Включено" if not r["enabled"] else "Выключено")


@router.callback_query(F.data.startswith("r:trg:"))
async def cb_trigger(call: CallbackQuery, db: Database, ub: UserBot):
    rid = rid_of(call)
    r = await db.rule(rid)
    order = list(TRIGGERS)
    nxt = order[(order.index(r["trigger"]) + 1) % len(order)]
    await db.execute("UPDATE rules SET trigger = ? WHERE id = ?", (nxt, rid))
    await ub.monitor.reload()
    await render_rule(call, db, rid)
    await call.answer(TRIGGERS[nxt])


@router.callback_query(F.data.startswith("r:ntf:"))
async def cb_notify(call: CallbackQuery, db: Database, ub: UserBot):
    rid = rid_of(call)
    await db.execute("UPDATE rules SET notify = 1 - notify WHERE id = ?", (rid,))
    await ub.monitor.reload()
    await render_rule(call, db, rid)
    await call.answer()


# --- ключевые слова ---

async def render_kw(event, db: Database, rid: int):
    r = await db.rule(rid)
    groups = json.loads(r["keywords"])
    lines = [f"🔑 <b>Ключевые слова — {h(r['name'])}</b>", ""]
    if groups:
        for i, g in enumerate(groups, 1):
            lines.append(("" if i == 1 else "<b>И</b> ") + f"<b>Группа {i}:</b> {h(', '.join(g))}")
    else:
        lines.append("<i>Пока нет ни одной группы слов.</i>")
    lines += ["", KW_HELP]
    rows = [[btn(f"🗑 Удалить группу {i}", f"r:kwd:{rid}:{i - 1}")] for i in range(1, len(groups) + 1)]
    await show(event, "\n".join(lines), kb(
        *rows,
        [btn("➕ Добавить группу слов", f"r:kwa:{rid}")],
        back(f"r:v:{rid}"),
    ))


@router.callback_query(F.data.startswith("r:kw:"))
async def cb_kw(call: CallbackQuery, db: Database):
    await render_kw(call, db, rid_of(call))
    await call.answer()


@router.callback_query(F.data.startswith("r:kwa:"))
async def cb_kw_add(call: CallbackQuery, state: FSMContext):
    rid = rid_of(call)
    prompt = await ask(call, "➕ <b>Новая группа слов</b>\n\nОтправьте слова через запятую, например:\n"
                             "<code>москв, мск, подмосков</code>\n\n" + KW_HELP, f"r:kw:{rid}")
    await state.set_state(Input.rule_kw)
    await state.update_data(prompt=prompt.message_id, rid=rid)
    await call.answer()


@router.message(Input.rule_kw, F.text)
async def in_kw(message: Message, state: FSMContext, db: Database, ub: UserBot):
    data = await state.get_data()
    terms = split_terms(message.text)
    error = _validate_terms(terms)
    if error:
        return await message.answer(error)
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    r = await db.rule(data["rid"])
    groups = json.loads(r["keywords"])
    groups.append(terms)
    await db.execute("UPDATE rules SET keywords = ? WHERE id = ?", (json.dumps(groups, ensure_ascii=False), r["id"]))
    await ub.monitor.reload()
    await render_kw(message, db, r["id"])


def _validate_terms(terms: list[str]) -> str | None:
    if not terms:
        return "Не нашёл ни одного слова. Перечислите их через запятую."
    try:
        compile_rule({"id": 0, "name": "", "trigger": "keywords", "keywords": json.dumps([terms]),
                      "exclude": "[]", "notify": 0, "forward_to": None, "reply_tpl": None,
                      "dm_tpl": None, "cooldown_h": 0})
    except Exception as e:  # noqa: BLE001 — ошибка в регулярке пользователя
        return f"Ошибка в регулярном выражении: <code>{h(e)}</code>"
    return None


@router.callback_query(F.data.startswith("r:kwd:"))
async def cb_kw_del(call: CallbackQuery, db: Database, ub: UserBot):
    _, _, rid, idx = call.data.split(":")
    r = await db.rule(int(rid))
    groups = json.loads(r["keywords"])
    if int(idx) < len(groups):
        groups.pop(int(idx))
    await db.execute("UPDATE rules SET keywords = ? WHERE id = ?", (json.dumps(groups, ensure_ascii=False), r["id"]))
    await ub.monitor.reload()
    await render_kw(call, db, r["id"])
    await call.answer("Удалено")


@router.callback_query(F.data.startswith("r:ex:"))
async def cb_exclude(call: CallbackQuery, state: FSMContext, db: Database):
    rid = rid_of(call)
    r = await db.rule(rid)
    current = ", ".join(json.loads(r["exclude"])) or "нет"
    prompt = await ask(call, "🚫 <b>Минус-слова</b>\n\nЕсли в заявке есть любое из них — фильтр её пропустит.\n"
                             f"Сейчас: <code>{h(current)}</code>\n\n"
                             "Отправьте новый список через запятую или <code>-</code>, чтобы очистить.", f"r:v:{rid}")
    await state.set_state(Input.rule_ex)
    await state.update_data(prompt=prompt.message_id, rid=rid)
    await call.answer()


@router.message(Input.rule_ex, F.text)
async def in_exclude(message: Message, state: FSMContext, db: Database, ub: UserBot):
    data = await state.get_data()
    terms = [] if message.text.strip() == "-" else split_terms(message.text)
    if terms and (error := _validate_terms(terms)):
        return await message.answer(error)
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute("UPDATE rules SET exclude = ? WHERE id = ?", (json.dumps(terms, ensure_ascii=False), data["rid"]))
    await ub.monitor.reload()
    await render_rule(message, db, data["rid"])


# --- прочие поля ---

@router.callback_query(F.data.startswith("r:cd:"))
async def cb_cooldown(call: CallbackQuery, state: FSMContext):
    rid = rid_of(call)
    prompt = await ask(call, "⏱ <b>Частота ЛС одному автору</b>\n\nНе писать одному человеку чаще, чем раз в N часов.\n"
                             "Отправьте число часов (0 — без ограничения).", f"r:v:{rid}")
    await state.set_state(Input.rule_cd)
    await state.update_data(prompt=prompt.message_id, rid=rid)
    await call.answer()


@router.message(Input.rule_cd, F.text)
async def in_cooldown(message: Message, state: FSMContext, db: Database, ub: UserBot):
    if not message.text.strip().isdigit():
        return await message.answer("Нужно целое число часов, например 24")
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute("UPDATE rules SET cooldown_h = ? WHERE id = ?", (min(int(message.text), 8760), data["rid"]))
    await ub.monitor.reload()
    await render_rule(message, db, data["rid"])


@router.callback_query(F.data.startswith("r:ren:"))
async def cb_rename(call: CallbackQuery, state: FSMContext):
    rid = rid_of(call)
    prompt = await ask(call, "✏️ Новое название фильтра:", f"r:v:{rid}")
    await state.set_state(Input.rule_rename)
    await state.update_data(prompt=prompt.message_id, rid=rid)
    await call.answer()


@router.message(Input.rule_rename, F.text)
async def in_rename(message: Message, state: FSMContext, db: Database, ub: UserBot):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute("UPDATE rules SET name = ? WHERE id = ?", (message.text.strip()[:64], data["rid"]))
    await ub.monitor.reload()
    await render_rule(message, db, data["rid"])


@router.callback_query(F.data.startswith("r:test:"))
async def cb_test(call: CallbackQuery, state: FSMContext):
    rid = rid_of(call)
    prompt = await ask(call, "🧪 <b>Проверка фильтра</b>\n\nПришлите или перешлите текст заявки — покажу, сработает ли фильтр.", f"r:v:{rid}")
    await state.set_state(Input.rule_test)
    await state.update_data(prompt=prompt.message_id, rid=rid)
    await call.answer()


@router.message(Input.rule_test)
async def in_test(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    rule = compile_rule(await db.rule(data["rid"]))
    text = message.text or message.caption or ""
    verdict = "✅ <b>Сработает</b>" if rule.match(text) else "❌ <b>Не сработает</b>"
    await message.answer(f"{verdict}\n\n<blockquote>{h(cut(text, 500))}</blockquote>",
                         reply_markup=kb([btn("🧪 Ещё раз", f"r:test:{rule.id}"), btn("« К фильтру", f"r:v:{rule.id}")]))


@router.callback_query(F.data.startswith("r:fwdx:"))
async def cb_forward_off(call: CallbackQuery, db: Database, ub: UserBot):
    rid = rid_of(call)
    await db.execute("UPDATE rules SET forward_to = NULL WHERE id = ?", (rid,))
    await ub.monitor.reload()
    await render_rule(call, db, rid)
    await call.answer("Пересылка выключена")


@router.callback_query(F.data.startswith("r:del:"))
async def cb_delete(call: CallbackQuery, db: Database):
    rid = rid_of(call)
    r = await db.rule(rid)
    await show(call, f"🗑 Удалить фильтр <b>{h(r['name'])}</b>?", kb(
        [btn("✅ Да, удалить", f"r:delok:{rid}"), btn("✖️ Отмена", f"r:v:{rid}")]
    ))
    await call.answer()


@router.callback_query(F.data.startswith("r:delok:"))
async def cb_delete_ok(call: CallbackQuery, db: Database, ub: UserBot):
    await db.execute("DELETE FROM rules WHERE id = ?", (rid_of(call),))
    await ub.monitor.reload()
    await render_list(call, db)
    await call.answer("Фильтр удалён")
