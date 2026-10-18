"""Второстепенные разделы: статистика, настройки, аккаунт, админы, настройка меню, пауза."""
import time

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...db import Database, now
from ...userbot.client import UserBot
from ..access import Access
from ..states import Input
from ..ui import SECTIONS, ask, back, btn, day_start, drop_prompt, h, kb, show
from .menu import render_main

router = Router(name="more")

# key -> (подпись, тип, мин, макс)
SETTINGS = {
    "notify_leads": ("🔔 Уведомления о заявках", "bool", 0, 0),
    "link_preview": ("🔗 Превью ссылок в шаблонах", "bool", 0, 0),
    "dm_delay": ("✉️ Пауза между ЛС авторам, сек", "int", 3, 3600),
    "quiet_hours": ("🌙 Тихие часы рассылок", "hours", 0, 0),
    "tz_offset": ("🕒 Часовой пояс, UTC±", "int", -12, 14),
    "retention_days": ("🗂 Хранить журналы, дней", "int", 1, 365),
}
STARTED = time.time()


# --- статистика ---

@router.callback_query(F.data == "x:stats")
async def cb_stats(call: CallbackQuery, db: Database):
    d0, d1, d7, d30 = day_start(db), day_start(db, 1), day_start(db, 6), day_start(db, 29)
    leads = await db.fetchone(
        "SELECT SUM(created_at >= ?) AS today, SUM(created_at >= ? AND created_at < ?) AS yesterday, "
        "SUM(created_at >= ?) AS week, COUNT(*) AS month FROM leads WHERE created_at >= ?",
        (d0, d1, d0, d7, d30),
    )
    top = await db.fetchall(
        "SELECT COALESCE(r.name, 'удалён') AS name, COUNT(*) AS n FROM leads l "
        "LEFT JOIN rules r ON r.id = l.rule_id WHERE l.created_at >= ? "
        "GROUP BY l.rule_id ORDER BY n DESC LIMIT 5",
        (d7,),
    )
    sends = await db.fetchone(
        "SELECT SUM(ok AND created_at >= ?) AS ok_today, SUM(NOT ok AND created_at >= ?) AS fail_today, "
        "SUM(ok) AS ok_week, SUM(NOT ok) AS fail_week FROM send_log WHERE created_at >= ?",
        (d0, d0, d7),
    )
    dms = await db.scalar("SELECT COUNT(*) FROM dm_log WHERE sent_at >= ?", (d0,))
    lines = [
        "📊 <b>Статистика</b>", "",
        "<b>📥 Заявки</b>",
        f"Сегодня: <b>{leads['today'] or 0}</b>   Вчера: <b>{leads['yesterday'] or 0}</b>",
        f"7 дней: <b>{leads['week'] or 0}</b>   30 дней: <b>{leads['month'] or 0}</b>",
    ]
    if top:
        lines += ["", "<b>🏆 Фильтры за 7 дней</b>"]
        lines += [f"{i}. {h(r['name'])} — {r['n']}" for i, r in enumerate(top, 1)]
    lines += [
        "", "<b>📣 Рассылки</b>",
        f"Сегодня: ✅ {sends['ok_today'] or 0}  ❌ {sends['fail_today'] or 0}",
        f"7 дней: ✅ {sends['ok_week'] or 0}  ❌ {sends['fail_week'] or 0}",
        "", f"✉️ Написали авторам сегодня: <b>{dms}</b>",
    ]
    await show(call, "\n".join(lines), kb([btn("🔄 Обновить", "x:stats")], back("m:more")))
    await call.answer()


# --- настройки ---

def setting_value(db: Database, key: str) -> str:
    kind = SETTINGS[key][1]
    value = db.get(key)
    if kind == "bool":
        return "вкл" if value else "выкл"
    if kind == "hours":
        return value or "нет"
    if key == "tz_offset":
        return f"{int(value):+d}"
    return str(value)


async def render_settings(event, db: Database):
    rows = [[btn(f"{label}: {setting_value(db, key)}", f"x:s:{key}")] for key, (label, *_) in SETTINGS.items()]
    await show(event, (
        "⚙️ <b>Настройки</b>\n\n"
        "• <b>Тихие часы</b> — в это время рассылки по расписанию не запускаются.\n"
        "• <b>Пауза между ЛС</b> — защита от спам-блока при автоответах авторам заявок.\n"
        "• <b>Часовой пояс</b> — для расписания, тихих часов и статистики."
    ), kb(*rows, back("m:more")))


@router.callback_query(F.data == "x:settings")
async def cb_settings(call: CallbackQuery, db: Database):
    await render_settings(call, db)
    await call.answer()


@router.callback_query(F.data.startswith("x:s:"))
async def cb_setting(call: CallbackQuery, state: FSMContext, db: Database):
    key = call.data.split(":")[2]
    label, kind, lo, hi = SETTINGS[key]
    if kind == "bool":
        await db.put(key, not db.get(key))
        await render_settings(call, db)
        return await call.answer("Сохранено")
    if kind == "hours":
        hint = "Отправьте интервал часов, например <code>23-8</code> (с 23:00 до 08:00), или <code>-</code>, чтобы выключить."
    else:
        hint = f"Отправьте число от {lo} до {hi}."
    prompt = await ask(call, f"<b>{label}</b>\nСейчас: {setting_value(db, key)}\n\n{hint}", "x:settings")
    await state.set_state(Input.setting)
    await state.update_data(prompt=prompt.message_id, key=key)
    await call.answer()


@router.message(Input.setting, F.text)
async def in_setting(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    key = data["key"]
    _, kind, lo, hi = SETTINGS[key]
    raw = message.text.strip().replace(" ", "")
    if kind == "hours":
        if raw == "-":
            value = ""
        else:
            parts = raw.split("-")
            if len(parts) != 2 or not all(p.isdigit() and 0 <= int(p) <= 23 for p in parts) or parts[0] == parts[1]:
                return await message.answer("Формат: <code>23-8</code> — два разных часа от 0 до 23")
            value = f"{int(parts[0])}-{int(parts[1])}"
    else:
        try:
            value = int(raw)
        except ValueError:
            return await message.answer(f"Нужно целое число от {lo} до {hi}")
        if not lo <= value <= hi:
            return await message.answer(f"Нужно целое число от {lo} до {hi}")
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.put(key, value)
    await render_settings(message, db)


# --- аккаунт и пауза ---

@router.callback_query(F.data == "x:account")
async def cb_account(call: CallbackQuery, db: Database, ub: UserBot):
    uptime = int(time.time() - STARTED)
    if ub.online:
        me = ub.me
        phone = f"+{me.phone[:4]}•••{me.phone[-2:]}" if me.phone else "скрыт"
        lines = [
            "👤 <b>Аккаунт юзербота</b>", "",
            "Статус: 🟢 подключён",
            f"Имя: {h(me.first_name)} {h(me.last_name or '')}",
            f"Username: @{h(me.username)}" if me.username else "Username: —",
            f"ID: <code>{me.id}</code>",
            f"Телефон: {phone}",
        ]
    else:
        lines = ["👤 <b>Аккаунт юзербота</b>", "", "Статус: 🔴 не подключён",
                 "Проверьте сессию: <code>python login.py</code> и перезапустите сервис."]
    chats = await db.scalar("SELECT COUNT(*) FROM chats")
    lines += [
        "",
        f"Режим: {'⏸ пауза' if db.get('paused') else '▶️ работает'}",
        f"Чатов в базе: {chats}",
        f"Очередь ЛС: {ub.monitor.dm_queue.qsize()}",
        f"Рассылок идёт: {len(ub.broadcaster.running)}",
        f"Аптайм: {uptime // 86400} д {uptime % 86400 // 3600} ч {uptime % 3600 // 60} мин",
    ]
    if ub.monitor.dm_blocked_until > now():
        lines.append("🚫 Авто-ЛС приостановлены из-за ограничения Telegram")
    await show(call, "\n".join(lines), kb(
        [btn("▶️ Снять с паузы" if db.get("paused") else "⏸ Поставить на паузу", "x:pause")],
        back("m:more"),
    ))
    await call.answer()


@router.callback_query(F.data == "x:pause")
async def cb_pause(call: CallbackQuery, db: Database, ub: UserBot):
    paused = not db.get("paused")
    await db.put("paused", paused)
    await render_main(call, db, ub)
    await call.answer("⏸ Юзербот на паузе: фильтры и рассылки остановлены" if paused else "▶️ Юзербот снова работает",
                      show_alert=True)


# --- настройка меню ---

@router.callback_query(F.data == "x:menu")
async def cb_menu_cfg(call: CallbackQuery, db: Database):
    main = db.get("main_menu")
    rows = [
        [btn(f"{'🏠 В главном' if key in main else '➕ В «Ещё»'} — {title}", f"x:mt:{key}")]
        for key, (title, _) in SECTIONS.items()
    ]
    await show(call, (
        "🎛 <b>Настройка меню</b>\n\n"
        "Нажмите на раздел, чтобы перенести его между главным меню и «Ещё». "
        "Порядок в главном меню — в порядке добавления."
    ), kb(*rows, [btn("♻️ По умолчанию", "x:mreset")], back("m:more")))
    await call.answer()


@router.callback_query(F.data.startswith("x:mt:"))
async def cb_menu_toggle(call: CallbackQuery, db: Database):
    key = call.data.split(":")[2]
    main = list(db.get("main_menu"))
    if key in main:
        main.remove(key)
    elif key in SECTIONS:
        main.append(key)
    await db.put("main_menu", main)
    await cb_menu_cfg(call, db)


@router.callback_query(F.data == "x:mreset")
async def cb_menu_reset(call: CallbackQuery, db: Database):
    from ...db import DEFAULT_SETTINGS

    await db.put("main_menu", list(DEFAULT_SETTINGS["main_menu"]))
    await cb_menu_cfg(call, db)


# --- админы ---

async def render_admins(event, access: Access):
    rows = [[btn(f"🔒 {uid} (из .env)", "noop")] for uid in sorted(access.env)]
    rows += [[btn(f"❌ {uid}", f"x:adel:{uid}")] for uid in sorted(access.extra - access.env)]
    await show(event, (
        "👥 <b>Администраторы</b>\n\n"
        "Админы из .env удалить нельзя. Нажмите ❌, чтобы забрать доступ."
    ), kb(*rows, [btn("➕ Добавить админа", "x:aadd")], back("m:more")))


@router.callback_query(F.data == "x:admins")
async def cb_admins(call: CallbackQuery, access: Access):
    await render_admins(call, access)
    await call.answer()


@router.callback_query(F.data == "x:aadd")
async def cb_admin_add(call: CallbackQuery, state: FSMContext):
    prompt = await ask(call, "➕ Отправьте Telegram ID нового админа или перешлите сюда любое его сообщение.\n\n"
                             "<i>Новый админ должен один раз нажать /start в этом боте.</i>", "x:admins")
    await state.set_state(Input.admin_add)
    await state.update_data(prompt=prompt.message_id)
    await call.answer()


@router.message(Input.admin_add)
async def in_admin_add(message: Message, state: FSMContext, db: Database, access: Access):
    uid = None
    origin = message.forward_origin
    if origin is not None and getattr(origin, "sender_user", None):
        uid = origin.sender_user.id
    elif message.text and message.text.strip().lstrip("-").isdigit():
        uid = int(message.text.strip())
    if not uid:
        return await message.answer("Не вижу ID. Отправьте число или перешлите сообщение (у человека не должна быть скрыта пересылка).")
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute("INSERT OR IGNORE INTO admins(user_id, added_at) VALUES(?, ?)", (uid, now()))
    access.extra.add(uid)
    await render_admins(message, access)


@router.callback_query(F.data.startswith("x:adel:"))
async def cb_admin_del(call: CallbackQuery, db: Database, access: Access):
    uid = int(call.data.split(":")[2])
    await db.execute("DELETE FROM admins WHERE user_id = ?", (uid,))
    access.extra.discard(uid)
    await render_admins(call, access)
    await call.answer("Доступ удалён")


# --- любой текст вне диалога ввода просто открывает меню ---

@router.message(StateFilter(None))
async def fallback(message: Message, db: Database, ub: UserBot):
    await render_main(message, db, ub)
