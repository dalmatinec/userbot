from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from ...db import Database
from ..ui import PAGE, back, btn, cut, day_start, fmt_ts, h, kb, message_link, pager, show

router = Router(name="leads")


async def lead_card(db: Database, lead_id: int, *, for_notify: bool = False) -> tuple[str, InlineKeyboardMarkup] | None:
    lead = await db.fetchone(
        "SELECT l.*, r.name AS rule_name, c.title AS chat_title, c.username AS chat_username "
        "FROM leads l LEFT JOIN rules r ON r.id = l.rule_id LEFT JOIN chats c ON c.id = l.chat_id "
        "WHERE l.id = ?",
        (lead_id,),
    )
    if not lead:
        return None
    name = h(lead["author_name"] or "")
    parts = []
    if lead["author_id"]:
        parts.append(f'<a href="tg://user?id={lead["author_id"]}">{name or "профиль"}</a>')
    elif name:
        parts.append(name)
    if lead["author_username"]:
        parts.append(f"@{h(lead['author_username'])}")
    if lead["author_id"]:
        parts.append(f"<code>{lead['author_id']}</code>")
    author = " ".join(parts) or "не определён"

    text = (
        f"📥 <b>{'Новая заявка' if for_notify else 'Заявка'} #{lead['id']}</b>\n\n"
        f"🎯 Фильтр: <b>{h(lead['rule_name'] or 'удалён')}</b>\n"
        f"💬 Чат: {h(lead['chat_title'] or lead['chat_id'])}\n"
        f"👤 Автор: {author}\n"
        f"🕒 {fmt_ts(lead['created_at'], db)}\n\n"
        f"<blockquote expandable>{h(cut(lead['text'], 3000)) or '<i>без текста</i>'}</blockquote>"
    )
    rows = []
    if lead["author_id"] or lead["author_username"]:
        rows.append([btn("✉️ Написать автору шаблоном", f"tp:ld:{lead_id}:0")])
    link = message_link(lead["chat_id"], lead["msg_id"], lead["chat_username"])
    if link:
        rows.append([btn("🔗 Открыть сообщение", url=link)])
    if not for_notify:
        rows.append(back("l:list:0", "« К заявкам"))
    return text, kb(*rows)


async def render_lead(event, db: Database, lead_id: int):
    card = await lead_card(db, lead_id)
    if not card:
        return await render_list(event, db)
    await show(event, *card)


async def render_list(event, db: Database, page: int = 0):
    total = await db.scalar("SELECT COUNT(*) FROM leads")
    today = await db.scalar("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (day_start(db),))
    rows = await db.fetchall(
        "SELECT id, author_name, author_username, text, created_at FROM leads ORDER BY id DESC LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    buttons = [
        [btn(f"{fmt_ts(r['created_at'], db)} · {cut(r['author_name'] or (r['author_username'] and '@' + r['author_username']) or '—', 14)} · {cut(r['text'], 22)}",
             f"l:v:{r['id']}")]
        for r in rows
    ]
    retention = db.get("retention_days")
    await show(event, (
        "📥 <b>Заявки</b>\n\n"
        f"Сегодня: <b>{today}</b>   Всего в журнале: <b>{total}</b>\n"
        f"<i>Журнал хранится {retention} дн.</i>"
    ), kb(*buttons, pager("l:list", page, total), back("m:main", "« Главное меню")))


@router.callback_query(F.data.startswith("l:list:"))
async def cb_list(call: CallbackQuery, db: Database):
    await render_list(call, db, int(call.data.split(":")[2]))
    await call.answer()


@router.callback_query(F.data.startswith("l:v:"))
async def cb_view(call: CallbackQuery, db: Database):
    await render_lead(call, db, int(call.data.split(":")[2]))
    await call.answer()
