"""Validação determinística de referências bíblicas (cânon protestante, 66 livros).

Valida: livro existe, capítulo dentro do limite do livro, versículos positivos e intervalo ordenado.
NÃO valida: quantidade de versículos de cada capítulo nem se o conteúdo citado confere com o texto.
Essa conferência é responsabilidade da revisão humana (etapa de aprovação). Limitação documentada.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# (nome canônico, capítulos, abreviações aceitas)
BOOKS: list[tuple[str, int, tuple[str, ...]]] = [
    ("Gênesis", 50, ("gn", "gen")), ("Êxodo", 40, ("ex", "exo")), ("Levítico", 27, ("lv", "lev")),
    ("Números", 36, ("nm", "num")), ("Deuteronômio", 34, ("dt", "deut")), ("Josué", 24, ("js", "jos")),
    ("Juízes", 21, ("jz", "jui")), ("Rute", 4, ("rt",)), ("1 Samuel", 31, ("1sm", "1 sm", "1sam")),
    ("2 Samuel", 24, ("2sm", "2 sm", "2sam")), ("1 Reis", 22, ("1rs", "1 rs")), ("2 Reis", 25, ("2rs", "2 rs")),
    ("1 Crônicas", 29, ("1cr", "1 cr")), ("2 Crônicas", 36, ("2cr", "2 cr")), ("Esdras", 10, ("ed", "esd")),
    ("Neemias", 13, ("ne", "nee")), ("Ester", 10, ("et", "est")), ("Jó", 42, ()),
    ("Salmos", 150, ("sl", "sal", "salmo")), ("Provérbios", 31, ("pv", "prov")), ("Eclesiastes", 12, ("ec", "ecl")),
    ("Cantares", 8, ("ct", "cantico dos canticos", "cânticos", "canticos")), ("Isaías", 66, ("is", "isa")),
    ("Jeremias", 52, ("jr", "jer")), ("Lamentações", 5, ("lm", "lam")), ("Ezequiel", 48, ("ez", "eze")),
    ("Daniel", 12, ("dn", "dan")), ("Oseias", 14, ("os", "oséias")), ("Joel", 3, ("jl",)), ("Amós", 9, ("am",)),
    ("Obadias", 1, ("ob",)), ("Jonas", 4, ("jn",)), ("Miqueias", 7, ("mq", "miquéias")), ("Naum", 3, ("na",)),
    ("Habacuque", 3, ("hc",)), ("Sofonias", 3, ("sf",)), ("Ageu", 2, ("ag",)), ("Zacarias", 14, ("zc", "zac")),
    ("Malaquias", 4, ("ml", "mal")), ("Mateus", 28, ("mt",)), ("Marcos", 16, ("mc",)), ("Lucas", 24, ("lc",)),
    ("João", 21, ("jo",)), ("Atos", 28, ("at",)), ("Romanos", 16, ("rm", "rom")),
    ("1 Coríntios", 16, ("1co", "1 co", "1cor")), ("2 Coríntios", 13, ("2co", "2 co", "2cor")),
    ("Gálatas", 6, ("gl", "gal")), ("Efésios", 6, ("ef",)), ("Filipenses", 4, ("fp", "fil")),
    ("Colossenses", 4, ("cl", "col")), ("1 Tessalonicenses", 5, ("1ts", "1 ts")),
    ("2 Tessalonicenses", 3, ("2ts", "2 ts")), ("1 Timóteo", 6, ("1tm", "1 tm")), ("2 Timóteo", 4, ("2tm", "2 tm")),
    ("Tito", 3, ("tt",)), ("Filemom", 1, ("fm",)), ("Hebreus", 13, ("hb", "heb")), ("Tiago", 5, ("tg",)),
    ("1 Pedro", 5, ("1pe", "1 pe")), ("2 Pedro", 3, ("2pe", "2 pe")), ("1 João", 5, ("1jo", "1 jo")),
    ("2 João", 1, ("2jo", "2 jo")), ("3 João", 1, ("3jo", "3 jo")), ("Judas", 1, ("jd",)),
    ("Apocalipse", 22, ("ap", "apoc")),
]


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s.replace(".", " ")).strip()


def _compact(s: str) -> str:
    return s.replace(" ", "")


_EXACT: dict[str, tuple[str, int]] = {}    # com acento (distingue "jó" de "jo")
_LOOSE: dict[str, tuple[str, int]] = {}    # sem acento e sem espaços
for _name, _ch, _abbrs in BOOKS:
    for alias in (_name, *_abbrs):
        _EXACT[alias.lower()] = (_name, _ch)
        key = _compact(_strip(alias))
        if key == "jo" and _name == "Jó":
            continue  # "Jo" sem acento é João; "Jó" só com acento
        _LOOSE.setdefault(key, (_name, _ch))
_LOOSE["jo"] = ("João", 21)

BOOK_PATTERN = r"(?:[1-3]\s?)?[A-Za-zÀ-ÿ]+(?:\s(?:dos\s)?[A-Za-zÀ-ÿ]+)?\.?"
REF_RE = re.compile(rf"(?P<book>{BOOK_PATTERN})\s+(?P<ch>\d{{1,3}})(?:[:.](?P<v1>\d{{1,3}})(?:\s?[-–]\s?(?P<v2>\d{{1,3}}))?)?")


@dataclass(frozen=True)
class Ref:
    book: str
    chapter: int
    verse_start: int | None = None
    verse_end: int | None = None

    def __str__(self) -> str:
        s = f"{self.book} {self.chapter}"
        if self.verse_start:
            s += f":{self.verse_start}"
            if self.verse_end and self.verse_end != self.verse_start:
                s += f"-{self.verse_end}"
        return s


def lookup_book(raw: str) -> tuple[str, int] | None:
    raw = raw.strip().rstrip(".")
    hit = _EXACT.get(raw.lower())
    if hit:
        return hit
    return _LOOSE.get(_compact(_strip(raw)))


def parse_ref(text: str) -> tuple[Ref | None, str]:
    """Retorna (Ref, '') se válida; (None, motivo) se inválida."""
    m = REF_RE.fullmatch(text.strip())
    if not m:
        return None, f"formato não reconhecido: '{text}'"
    book = lookup_book(m.group("book"))
    if not book:
        return None, f"livro desconhecido: '{m.group('book')}'"
    name, max_ch = book
    ch = int(m.group("ch"))
    if not 1 <= ch <= max_ch:
        return None, f"{name} tem {max_ch} capítulo(s); recebido {ch}"
    v1 = int(m.group("v1")) if m.group("v1") else None
    v2 = int(m.group("v2")) if m.group("v2") else None
    if v1 is not None and v1 < 1:
        return None, "versículo deve ser >= 1"
    if v1 and v2 and v2 < v1:
        return None, f"intervalo invertido: {v1}-{v2}"
    return Ref(name, ch, v1, v2), ""


def find_refs(text: str) -> list[str]:
    """Extrai referências entre parênteses: '(1 Samuel 17:45)'. É o formato exigido nos roteiros."""
    return [m.strip() for m in re.findall(r"\(([^()]{3,40}?\d{1,3}(?:[:.]\d{1,3}(?:\s?[-–]\s?\d{1,3})?)?)\)", text)]
