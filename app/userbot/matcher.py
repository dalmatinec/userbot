"""Компиляция правил и быстрая проверка текста заявки.

Ключевые слова:
  * обычное слово ищется с начала слова: «москв» найдёт «Москва», «Москве», «москвы»;
  * слово целиком — в кавычках: "спб" не найдёт «спбгу»;
  * регулярное выражение — с префиксом re: например  re:айфон\\s?1[3-6]
Группы: ИЛИ внутри группы, И между группами («город» И «товар»).

Команды задаются свои:
  * со слэшем (/start, /price) — ищутся в любом месте текста, в т.ч. /start@bot и «написал: /start»;
  * без слэша (старт, меню) — сообщение (или строка сообщения) должно начинаться с этого слова.
"""
import json
import re
from dataclasses import dataclass, field

_WORD = r"[\w\-]"


def normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def _compile_terms(terms: list[str]) -> re.Pattern | None:
    parts = []
    for raw in terms:
        term = raw.strip()
        if not term:
            continue
        if term.startswith("re:"):
            parts.append(f"(?:{term[3:]})")
            continue
        exact = len(term) > 2 and (
            (term[0] == term[-1] and term[0] in "\"'") or (term[0] == "«" and term[-1] == "»")
        )
        if exact:
            term = term[1:-1]
        word = re.escape(normalize(term))
        tail = rf"(?!{_WORD})" if exact else ""
        parts.append(rf"(?<!{_WORD}){word}{tail}")
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)


def _compile_commands(commands: list[str]) -> re.Pattern | None:
    parts = []
    for raw in commands:
        cmd = normalize(raw.strip())
        if not cmd:
            continue
        if cmd.startswith("/"):
            parts.append(rf"(?<![\w/]){re.escape(cmd)}(?:@\w+)?(?!{_WORD})")
        else:
            parts.append(rf"^\s*{re.escape(cmd)}(?!{_WORD})")
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE | re.MULTILINE)


def split_terms(text: str) -> list[str]:
    """Разбивает ввод админа на слова: через запятую, точку с запятой или с новой строки."""
    return [t.strip() for t in re.split(r"[,;\n]", text) if t.strip()]


@dataclass
class CompiledRule:
    id: int
    name: str
    trigger: str
    groups: list[re.Pattern] = field(default_factory=list)
    exclude: re.Pattern | None = None
    commands: re.Pattern | None = None
    notify: bool = True
    forward_to: int | None = None
    reply_tpl: int | None = None
    dm_tpl: int | None = None
    cooldown_h: int = 24
    delay_sec: int | None = None

    def match(self, text: str) -> bool:
        norm = normalize(text or "")
        if self.exclude and self.exclude.search(norm):
            return False
        if self.trigger == "joined":
            return False  # срабатывает на вступление, а не на текст
        if self.trigger == "any":
            return True
        if self.trigger == "commands":
            return bool(self.commands and self.commands.search(norm))
        if not self.groups:
            return False
        return all(p.search(norm) for p in self.groups)


def compile_rule(row) -> CompiledRule:
    groups = [p for p in (_compile_terms(g) for g in json.loads(row["keywords"])) if p]
    return CompiledRule(
        id=row["id"],
        name=row["name"],
        trigger=row["trigger"],
        groups=groups,
        exclude=_compile_terms(json.loads(row["exclude"])),
        commands=_compile_commands(json.loads(row["commands"]) if "commands" in row.keys() else []),
        notify=bool(row["notify"]),
        forward_to=row["forward_to"],
        reply_tpl=row["reply_tpl"],
        dm_tpl=row["dm_tpl"],
        cooldown_h=row["cooldown_h"],
        delay_sec=row["delay_sec"],
    )
