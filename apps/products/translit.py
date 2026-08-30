"""Транслитерация и слаги (§2 ТЗ): slug из title, дедупликация «-2», «-3»."""

import re

CYR_TO_LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def translit(text: str) -> str:
    out = []
    for ch in (text or "").lower():
        if ch in CYR_TO_LAT:
            out.append(CYR_TO_LAT[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    return "".join(out)


def slugify(text: str, max_length: int = 120) -> str:
    slug = re.sub(r"-{2,}", "-", translit(text)).strip("-")
    return slug[:max_length].rstrip("-") or "item"


def unique_slug(model, text: str, slug_field: str = "slug", max_length: int = 120, exclude_pk=None) -> str:
    """base → base-2 → base-3… Проверяет занятость в БД."""
    base = slugify(text, max_length)
    qs = model.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    candidate, n = base, 1
    while qs.filter(**{slug_field: candidate}).exists():
        n += 1
        suffix = f"-{n}"
        candidate = base[: max_length - len(suffix)] + suffix
    return candidate
