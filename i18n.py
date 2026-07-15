#!/usr/bin/env python3
"""Small source-string localization helper for BudgetPilot.

Slovak is the source language and the fallback key. English translations live
in JSON so templates, Python code, inline JavaScript, and response text all use
the same catalog without adding a framework dependency.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


DEFAULT_LANGUAGE = "sk"
SUPPORTED_LANGUAGES = {
    "sk": "Slovencina",
    "en": "English",
}
LANGUAGE_COOKIE = "budgetpilot_lang"
LANGUAGE_SESSION_KEY = "budgetpilot_language"
TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"


def normalize_language(value: str | None) -> str:
    lang = (value or "").strip().lower().split("-", 1)[0]
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


@lru_cache(maxsize=None)
def load_catalog(language: str) -> dict[str, str]:
    lang = normalize_language(language)
    path = TRANSLATIONS_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def translate(text: str, language: str | None = None, **values) -> str:
    key = str(text)
    lang = normalize_language(language)
    if lang == DEFAULT_LANGUAGE:
        value = load_catalog(DEFAULT_LANGUAGE).get(key, key)
    else:
        value = (
            load_catalog(lang).get(key)
            or load_catalog(DEFAULT_LANGUAGE).get(key)
            or key
        )
    if values:
        try:
            return value.format(**values)
        except Exception:
            return value
    return value


def missing_keys(language: str) -> list[str]:
    base_keys = set(load_catalog(DEFAULT_LANGUAGE))
    other_keys = set(load_catalog(language))
    return sorted(base_keys - other_keys)


def _replacement_map(language: str) -> dict[str, str]:
    lang = normalize_language(language)
    if lang == DEFAULT_LANGUAGE:
        return {}
    replacements = {}
    base = load_catalog(DEFAULT_LANGUAGE)
    catalog = load_catalog(lang)
    for key in sorted(base.keys(), key=len, reverse=True):
        translated = catalog.get(key)
        if translated and translated != key:
            replacements[key] = translated
    return replacements


def translate_html(html: str, language: str) -> str:
    """Translate rendered HTML by exact source-string replacement.

    The catalog contains only stable UI copy. User data is not translated
    unless it exactly matches a UI phrase already present in the catalog.
    """
    lang = normalize_language(language)
    if lang == DEFAULT_LANGUAGE or not html:
        return html

    result = html
    result = re.sub(r'<html lang="[^"]*"', f'<html lang="{lang}"', result, count=1)
    for source, translated in _replacement_map(lang).items():
        result = result.replace(source, translated)
    return result
