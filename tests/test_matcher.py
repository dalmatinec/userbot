import json

from app.userbot.broadcaster import in_quiet_hours
from app.userbot.matcher import compile_rule, split_terms


def rule(trigger="keywords", groups=(), exclude=(), commands=()):
    return compile_rule({
        "id": 1, "name": "t", "trigger": trigger, "commands": json.dumps(list(commands)),
        "keywords": json.dumps([list(g) for g in groups]), "exclude": json.dumps(list(exclude)),
        "notify": 1, "forward_to": None, "reply_tpl": None, "dm_tpl": None, "cooldown_h": 24,
    })


def test_city_and_product():
    r = rule(groups=[["москв", "мск"], ["айфон", "iphone"]])
    assert r.match("Нужен iPhone 15, я из Москвы")
    assert r.match("МСК, айфоны есть?")
    assert not r.match("Нужен айфон, я из Казани")
    assert not r.match("Москва, нужен самсунг")


def test_prefix_not_inside_word():
    r = rule(groups=[["кот"]])
    assert r.match("Продам котёнка")
    assert not r.match("Нужен скотч")


def test_exact_and_yo():
    r = rule(groups=[['"спб"', "ёлк"]])
    assert r.match("Доставка в СПб")
    assert not r.match("учусь в спбгу")
    assert r.match("Купить елку")


def test_regex_and_exclude():
    r = rule(groups=[["re:айфон\\s?1[3-6]"]], exclude=["б/у"])
    assert r.match("айфон 15 новый")
    assert not r.match("айфон 12")
    assert not r.match("айфон 15 б/у")


def test_custom_commands():
    r = rule("commands", commands=["/start", "/price", "старт"])
    assert r.match("/start")
    assert r.match("/START@shop_bot")
    assert r.match("Пользователь написал: /start ref123")
    assert r.match("/price айфон")
    assert r.match("Старт")
    assert r.match("Новая заявка\nстарт")
    assert not r.match("/restart")
    assert not r.match("/starter")
    assert not r.match("хочу на старт")
    assert not rule("commands").match("/start")  # команды не заданы


def test_any():
    assert rule("any").match("что угодно")
    assert not rule("any", exclude=["спам"]).match("это спам")


def test_empty_keywords_never_match():
    assert not rule(groups=[]).match("что угодно")


def test_split_terms():
    assert split_terms("москв, мск;\nспб ,, ") == ["москв", "мск", "спб"]


def test_quiet_hours(monkeypatch):
    import time

    def at(hour):
        monkeypatch.setattr(time, "gmtime", lambda *_: time.struct_time((2026, 1, 1, hour, 0, 0, 0, 1, 0)))

    at(22)  # 01:00 по UTC+3
    assert in_quiet_hours("23-8", 3)
    at(9)  # 12:00
    assert not in_quiet_hours("23-8", 3)
    assert in_quiet_hours("10-14", 3)
    assert not in_quiet_hours("", 3)
