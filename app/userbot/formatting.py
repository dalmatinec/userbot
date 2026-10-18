"""Перевод entities из Bot API (как их присылает aiogram) в entities Telethon.

Шаблон сохраняется ровно таким, каким админ отправил его боту: жирный, курсив,
спойлеры, ссылки, цитаты, премиум-эмодзи — всё переносится без HTML-разметки.
Смещения в обоих API считаются в UTF-16, поэтому конвертация точная.
"""
import json

from telethon.tl import types as t

_SIMPLE = {
    "bold": t.MessageEntityBold,
    "italic": t.MessageEntityItalic,
    "underline": t.MessageEntityUnderline,
    "strikethrough": t.MessageEntityStrike,
    "spoiler": t.MessageEntitySpoiler,
    "code": t.MessageEntityCode,
}


def to_telethon(entities_json: str) -> list:
    result = []
    for e in json.loads(entities_json or "[]"):
        kind, off, ln = e["type"], e["offset"], e["length"]
        if kind in _SIMPLE:
            result.append(_SIMPLE[kind](off, ln))
        elif kind == "pre":
            result.append(t.MessageEntityPre(off, ln, e.get("language") or ""))
        elif kind == "text_link":
            result.append(t.MessageEntityTextUrl(off, ln, e["url"]))
        elif kind == "custom_emoji":
            result.append(t.MessageEntityCustomEmoji(off, ln, int(e["custom_emoji_id"])))
        elif kind == "blockquote":
            result.append(t.MessageEntityBlockquote(off, ln))
        elif kind == "expandable_blockquote":
            result.append(t.MessageEntityBlockquote(off, ln, collapsed=True))
        # url, mention, hashtag и т.п. Telegram распознаёт сам
    return result


def dump_bot_entities(entities) -> str:
    if not entities:
        return "[]"
    return json.dumps(
        [e.model_dump(exclude_none=True, exclude={"user"}) for e in entities if e.type != "text_mention"],
        ensure_ascii=False,
    )
