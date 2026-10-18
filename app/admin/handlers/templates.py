"""Шаблоны сообщений: текст с форматированием и/или медиа. Плюс универсальный выбор шаблона."""
import json
import shutil
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, MessageEntity

from ...config import Config
from ...db import Database, now
from ...userbot.client import UserBot
from ...userbot.formatting import dump_bot_entities
from ..states import Input
from ..ui import PAGE, ask, back, btn, cut, drop_prompt, h, kb, pager, show

router = Router(name="templates")

MEDIA_ICONS = {"photo": "🖼", "video": "🎬", "animation": "🎞", "document": "📎", "audio": "🎵", "voice": "🎤"}
CONTENT_HINT = (
    "Отправьте сообщение так, как оно должно выглядеть: текст с форматированием "
    "(жирный, курсив, ссылки, спойлеры, цитаты, премиум-эмодзи) и/или одно фото, видео, GIF, файл, аудио или голосовое с подписью.\n\n"
    "<i>Альбомы не поддерживаются — сохранится только первое медиа.</i>"
)

# mode -> (заголовок, несколько, куда вернуться)
PICK_MODES = {
    "rr": ("💬 Шаблон ответа в группе", False, "r:v:{}"),
    "rd": ("✉️ Шаблон ЛС автору заявки", False, "r:v:{}"),
    "bt": ("📝 Шаблоны рассылки", True, "b:v:{}"),
    "ld": ("✉️ Чем ответить автору?", False, "l:v:{}"),
}


def tid_of(call: CallbackQuery) -> int:
    return int(call.data.split(":")[2])


def media_label(t) -> str:
    return f"{MEDIA_ICONS.get(t['media_type'], '')} " if t["media_path"] else ""


async def render_list(event, db: Database, page: int = 0):
    total = await db.scalar("SELECT COUNT(*) FROM templates")
    rows = await db.fetchall(
        "SELECT id, name, media_path, media_type FROM templates ORDER BY id DESC LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    buttons = [[btn(f"{media_label(t)}{cut(t['name'], 34)}", f"t:v:{t['id']}")] for t in rows]
    await show(event, (
        "📝 <b>Шаблоны сообщений</b>\n\n"
        "Заготовки для рассылок, ответов в группах и личных сообщений авторам заявок.\n\n"
        f"Всего шаблонов: <b>{total}</b>"
    ), kb(*buttons, pager("t:list", page, total), [btn("➕ Новый шаблон", "t:new")], back("m:main", "« Главное меню")))


async def render_template(event, db: Database, tid: int):
    t = await db.template(tid)
    if not t:
        return await render_list(event, db)
    used_r = await db.scalar("SELECT COUNT(*) FROM rules WHERE reply_tpl = ? OR dm_tpl = ?", (tid, tid))
    used_b = await db.scalar("SELECT COUNT(*) FROM broadcast_templates WHERE template_id = ?", (tid,))
    media = f"{MEDIA_ICONS.get(t['media_type'], '📎')} {t['media_type']}" if t["media_path"] else "нет"
    text = (
        f"📝 <b>{h(t['name'])}</b>\n\n"
        f"Медиа: {media}\n"
        f"Длина текста: {len(t['text'])} симв.\n"
        f"Используется: фильтров — {used_r}, рассылок — {used_b}\n\n"
        f"<blockquote>{h(cut(t['text'], 700)) or '<i>без текста</i>'}</blockquote>"
    )
    await show(event, text, kb(
        [btn("👁 Предпросмотр", f"t:pv:{tid}"), btn("🧪 Тест в «Избранное»", f"t:me:{tid}")],
        [btn("✏️ Изменить содержимое", f"t:edit:{tid}"), btn("🏷 Название", f"t:ren:{tid}")],
        [btn("🗑 Удалить", f"t:del:{tid}"), btn("« К шаблонам", "t:list:0")],
    ))


@router.callback_query(F.data.startswith("t:list:"))
async def cb_list(call: CallbackQuery, db: Database):
    await render_list(call, db, int(call.data.split(":")[2]))
    await call.answer()


@router.callback_query(F.data.startswith("t:v:"))
async def cb_view(call: CallbackQuery, db: Database):
    await render_template(call, db, tid_of(call))
    await call.answer()


@router.callback_query(F.data == "t:new")
async def cb_new(call: CallbackQuery, state: FSMContext):
    prompt = await ask(call, "➕ <b>Новый шаблон</b>\n\nШаг 1/2. Напишите название шаблона:", "t:list:0")
    await state.set_state(Input.tpl_name)
    await state.update_data(prompt=prompt.message_id)
    await call.answer()


@router.message(Input.tpl_name, F.text)
async def in_name(message: Message, state: FSMContext):
    data = await state.get_data()
    await drop_prompt(message, data.get("prompt"))
    prompt = await message.answer(f"Шаг 2/2. {CONTENT_HINT}", reply_markup=kb(back("✖️ Отмена", "t:list:0")))
    await state.set_state(Input.tpl_content)
    await state.update_data(prompt=prompt.message_id, name=message.text.strip()[:64], tid=None)


@router.callback_query(F.data.startswith("t:edit:"))
async def cb_edit(call: CallbackQuery, state: FSMContext):
    tid = tid_of(call)
    prompt = await ask(call, f"✏️ <b>Новое содержимое шаблона</b>\n\n{CONTENT_HINT}", f"t:v:{tid}")
    await state.set_state(Input.tpl_content)
    await state.update_data(prompt=prompt.message_id, tid=tid)
    await call.answer()


async def save_media(message: Message, cfg: Config, tid: int) -> tuple[str, str] | None:
    """Скачивает медиа из сообщения на диск, чтобы юзербот мог его отправить."""
    m = message
    if m.photo:
        f, kind, name = m.photo[-1], "photo", "photo.jpg"
    elif m.animation:
        f, kind, name = m.animation, "animation", m.animation.file_name or "animation.mp4"
    elif m.video:
        f, kind, name = m.video, "video", m.video.file_name or "video.mp4"
    elif m.document:
        f, kind, name = m.document, "document", m.document.file_name or "file"
    elif m.audio:
        f, kind, name = m.audio, "audio", m.audio.file_name or "audio.mp3"
    elif m.voice:
        f, kind, name = m.voice, "voice", "voice.ogg"
    else:
        return None
    folder = cfg.media_dir / f"{tid}_{f.file_unique_id}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(name).name
    await message.bot.download(f, destination=path)
    return str(path), kind


def remove_media(path: str | None) -> None:
    if path:
        shutil.rmtree(Path(path).parent, ignore_errors=True)


@router.message(Input.tpl_content)
async def in_content(message: Message, state: FSMContext, db: Database, cfg: Config):
    data = await state.get_data()
    text = message.text or message.caption or ""
    entities = dump_bot_entities(message.entities or message.caption_entities)
    has_media = any((message.photo, message.animation, message.video, message.document, message.audio, message.voice))
    if not text and not has_media:
        return await message.answer("Это сообщение не подходит. Пришлите текст или медиа.")

    tid = data.get("tid")
    old = await db.template(tid) if tid else None
    if not tid:
        tid = await db.execute("INSERT INTO templates(name, created_at) VALUES(?, ?)", (data["name"], now()))

    media_path = media_type = None
    if has_media:
        try:
            saved = await save_media(message, cfg, tid)
        except TelegramBadRequest as e:
            if not old:
                await db.execute("DELETE FROM templates WHERE id = ?", (tid,))
            return await message.answer(f"Не удалось скачать файл (боты скачивают до 20 МБ): {h(e)}")
        media_path, media_type = saved
    if old and old["media_path"] != media_path:
        remove_media(old["media_path"])

    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute(
        "UPDATE templates SET text = ?, entities = ?, media_path = ?, media_type = ? WHERE id = ?",
        (text, entities, media_path, media_type, tid),
    )
    await message.answer("✅ Шаблон сохранён")
    await render_template(message, db, tid)


@router.callback_query(F.data.startswith("t:ren:"))
async def cb_rename(call: CallbackQuery, state: FSMContext):
    tid = tid_of(call)
    prompt = await ask(call, "🏷 Новое название шаблона:", f"t:v:{tid}")
    await state.set_state(Input.tpl_rename)
    await state.update_data(prompt=prompt.message_id, tid=tid)
    await call.answer()


@router.message(Input.tpl_rename, F.text)
async def in_rename(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    await state.clear()
    await drop_prompt(message, data.get("prompt"))
    await db.execute("UPDATE templates SET name = ? WHERE id = ?", (message.text.strip()[:64], data["tid"]))
    await render_template(message, db, data["tid"])


async def send_preview(bot: Bot, chat_id: int, t) -> None:
    """Показывает шаблон так, как его увидят получатели."""
    entities = [MessageEntity(**e) for e in json.loads(t["entities"])]
    text = t["text"] or None
    if not t["media_path"]:
        await bot.send_message(chat_id, text or "—", entities=entities, parse_mode=None, disable_web_page_preview=True)
        return
    file = FSInputFile(t["media_path"])
    common = {"caption": text, "caption_entities": entities, "parse_mode": None}
    sender = {
        "photo": bot.send_photo, "video": bot.send_video, "animation": bot.send_animation,
        "audio": bot.send_audio, "voice": bot.send_voice,
    }.get(t["media_type"], bot.send_document)
    await sender(chat_id, file, **common)


@router.callback_query(F.data.startswith("t:pv:"))
async def cb_preview(call: CallbackQuery, db: Database):
    t = await db.template(tid_of(call))
    try:
        await send_preview(call.bot, call.from_user.id, t)
    except (TelegramBadRequest, FileNotFoundError) as e:
        return await call.answer(f"Не получилось: {e}"[:190], show_alert=True)
    await call.answer()
    # меню переносим под предпросмотр, чтобы оно оставалось последним сообщением
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await render_template(call.message, db, t["id"])


@router.callback_query(F.data.startswith("t:me:"))
async def cb_test_me(call: CallbackQuery, db: Database, ub: UserBot):
    if not ub.online:
        return await call.answer("Юзербот не подключён", show_alert=True)
    t = await db.template(tid_of(call))
    try:
        await ub.send_template("me", t)
    except Exception as e:  # noqa: BLE001 — показываем админу любую причину
        return await call.answer(f"Ошибка: {e.__class__.__name__}: {e}"[:190], show_alert=True)
    await call.answer("Отправлено в «Избранное» аккаунта ✅", show_alert=True)


@router.callback_query(F.data.startswith("t:del:"))
async def cb_delete(call: CallbackQuery, db: Database):
    t = await db.template(tid_of(call))
    await show(call, f"🗑 Удалить шаблон <b>{h(t['name'])}</b>?\nОн пропадёт из фильтров и рассылок.", kb(
        [btn("✅ Да, удалить", f"t:delok:{t['id']}"), btn("✖️ Отмена", f"t:v:{t['id']}")]
    ))
    await call.answer()


@router.callback_query(F.data.startswith("t:delok:"))
async def cb_delete_ok(call: CallbackQuery, db: Database, ub: UserBot):
    t = await db.template(tid_of(call))
    if t:
        await db.execute("DELETE FROM templates WHERE id = ?", (t["id"],))
        remove_media(t["media_path"])
        await ub.monitor.reload()
    await render_list(call, db)
    await call.answer("Шаблон удалён")


# --- выбор шаблона для фильтров, рассылок и ответа на заявку ---

async def _selected(db: Database, mode: str, obj: int) -> set[int]:
    if mode in ("rr", "rd"):
        r = await db.rule(obj)
        value = r["reply_tpl"] if mode == "rr" else r["dm_tpl"]
        return {value} if value else set()
    if mode == "bt":
        return set(await db.broadcast_template_ids(obj))
    return set()


async def render_picker(event, db: Database, mode: str, obj: int, page: int):
    title, multi, back_to = PICK_MODES[mode]
    total = await db.scalar("SELECT COUNT(*) FROM templates")
    rows = await db.fetchall(
        "SELECT id, name, media_path, media_type FROM templates ORDER BY id DESC LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    selected = await _selected(db, mode, obj)
    buttons = [
        [btn(f"{'✅ ' if t['id'] in selected else ''}{media_label(t)}{cut(t['name'], 32)}",
             f"tps:{mode}:{obj}:{page}:{t['id']}")]
        for t in rows
    ]
    hint = "Можно выбрать несколько — они будут чередоваться между чатами и запусками." if multi else "Выберите шаблон."
    if not total:
        hint = "<i>Шаблонов пока нет — создайте их в разделе «📝 Шаблоны».</i>"
    clear = [btn("🚫 Не использовать", f"tpx:{mode}:{obj}")] if mode in ("rr", "rd") else None
    await show(event, f"<b>{title}</b>\n\n{hint}", kb(
        *buttons,
        pager(f"tp:{mode}:{obj}", page, total),
        clear,
        [btn("➕ Новый шаблон", "t:new")] if not total else None,
        back(back_to.format(obj), "✅ Готово" if multi else "« Назад"),
    ))


async def _back(event, db: Database, ub: UserBot, mode: str, obj: int):
    from . import broadcasts, leads, rules

    if mode in ("rr", "rd"):
        await rules.render_rule(event, db, obj)
    elif mode == "bt":
        await broadcasts.render_broadcast(event, db, obj, ub)
    else:
        await leads.render_lead(event, db, obj)


@router.callback_query(F.data.startswith("tp:"))
async def cb_picker(call: CallbackQuery, db: Database):
    _, mode, obj, page = call.data.split(":")
    await render_picker(call, db, mode, int(obj), int(page))
    await call.answer()


@router.callback_query(F.data.startswith("tps:"))
async def cb_pick(call: CallbackQuery, db: Database, ub: UserBot):
    _, mode, obj, page, tid = call.data.split(":")
    obj, tid = int(obj), int(tid)
    if mode in ("rr", "rd"):
        col = "reply_tpl" if mode == "rr" else "dm_tpl"
        await db.execute(f"UPDATE rules SET {col} = ? WHERE id = ?", (tid, obj))
        await ub.monitor.reload()
        await _back(call, db, ub, mode, obj)
        return await call.answer("Сохранено")
    if mode == "bt":
        exists = await db.scalar(
            "SELECT 1 FROM broadcast_templates WHERE broadcast_id = ? AND template_id = ?", (obj, tid)
        )
        if exists:
            await db.execute("DELETE FROM broadcast_templates WHERE broadcast_id = ? AND template_id = ?", (obj, tid))
        else:
            await db.execute("INSERT INTO broadcast_templates(broadcast_id, template_id) VALUES(?, ?)", (obj, tid))
        await render_picker(call, db, mode, obj, int(page))
        return await call.answer("Убрано" if exists else "Добавлено")
    # ld — ответ автору заявки
    lead = await db.fetchone("SELECT * FROM leads WHERE id = ?", (obj,))
    if not lead or not ub.online:
        return await call.answer("Юзербот не подключён" if lead else "Заявка не найдена", show_alert=True)
    pos = ub.monitor.queue_manual_dm(lead["author_id"], lead["author_username"], tid, lead["author_name"] or "автор")
    await _back(call, db, ub, mode, obj)
    await call.answer(f"Поставлено в очередь отправки (№{pos})", show_alert=True)


@router.callback_query(F.data.startswith("tpx:"))
async def cb_clear(call: CallbackQuery, db: Database, ub: UserBot):
    _, mode, obj = call.data.split(":")
    col = "reply_tpl" if mode == "rr" else "dm_tpl"
    await db.execute(f"UPDATE rules SET {col} = NULL WHERE id = ?", (int(obj),))
    await ub.monitor.reload()
    await _back(call, db, ub, mode, int(obj))
    await call.answer("Отключено")
