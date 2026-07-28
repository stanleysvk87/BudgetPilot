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


# Attributes whose value is human-readable UI copy, and therefore the only
# attributes it is safe to translate.
#
# Everything else -- above all `<option value>` / `<input value>`, which are
# the *machine* values a form posts back -- is left byte-for-byte alone. A
# blind whole-document str.replace() used to rewrite them too, because the
# catalog legitimately maps machine-ish source strings that also appear as
# option values: "once" -> "one-time", "custom_months" -> "custom",
# "Iné" -> "Other". Submitting an English form then stored
# {"name": "Other", "frequency": "one-time"}, which silently discarded the
# user's own payment name (make_payment_from_form() only reads the custom
# name field for type == "Iné") and made the payment invisible in every
# month (obligations.occurrence_matches_frequency() returns False for an
# unknown frequency). See docs/LOCALIZATION.md.
TRANSLATABLE_ATTRS = {
    "alt",
    "aria-description",
    "aria-label",
    "aria-placeholder",
    "aria-roledescription",
    "aria-valuetext",
    "content",
    "label",
    "placeholder",
    "title",
}

# One HTML tag, tolerating ">" inside a quoted attribute value.
_TAG_RE = re.compile(r"""<(?:[^<>"']|"[^"]*"|'[^']*')*>""", re.DOTALL)
# name="value" / name='value' inside a tag.
_ATTR_RE = re.compile(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)')""")
# Inline <script>/<style> blocks, kept whole so their contents aren't parsed
# as markup (JS string literals contain "<", ">" and quotes of their own).
_SCRIPT_STYLE_RE = re.compile(
    r"(<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>)",
    re.DOTALL | re.IGNORECASE,
)


def _replace_all(text: str, replacements: dict[str, str]) -> str:
    for source, translated in replacements.items():
        text = text.replace(source, translated)
    return text


def _translate_tag(tag: str, replacements: dict[str, str]) -> str:
    """Translate only the whitelisted attribute values of a single tag.

    Tag names, attribute names, unquoted values and every non-whitelisted
    attribute are returned untouched.
    """
    def replace_attr(match: re.Match) -> str:
        name = match.group(1).lower()
        if name not in TRANSLATABLE_ATTRS:
            return match.group(0)
        quote = match.group(2)[0]
        raw = match.group(3) if quote == '"' else match.group(4)
        translated = _replace_all(raw, replacements)
        if translated == raw:
            return match.group(0)
        # A translation containing the surrounding quote character would
        # otherwise break out of the attribute (e.g. the EN catalog's
        # 'Name for "Other"').
        translated = translated.replace(quote, "&quot;" if quote == '"' else "&#39;")
        return f"{match.group(1)}={quote}{translated}{quote}"

    return _ATTR_RE.sub(replace_attr, tag)


def translate_html(html: str, language: str) -> str:
    """Translate rendered HTML by exact source-string replacement, applied
    to text content only -- never to markup or to attribute values that
    carry machine data (see TRANSLATABLE_ATTRS).

    The catalog contains only stable UI copy. User data is not translated
    unless it exactly matches a UI phrase already present in the catalog.
    """
    lang = normalize_language(language)
    if lang == DEFAULT_LANGUAGE or not html:
        return html

    replacements = _replacement_map(lang)
    if not replacements:
        return html

    result = re.sub(r'<html lang="[^"]*"', f'<html lang="{lang}"', html, count=1)

    out: list[str] = []
    for chunk in _SCRIPT_STYLE_RE.split(result):
        if not chunk:
            continue
        if _SCRIPT_STYLE_RE.fullmatch(chunk):
            # The app's own inline scripts build UI copy (headings, button
            # labels) as JS string literals and also match on it, so an
            # inline script block keeps the plain whole-text replacement.
            out.append(_replace_all(chunk, replacements))
            continue
        pos = 0
        for match in _TAG_RE.finditer(chunk):
            out.append(_replace_all(chunk[pos:match.start()], replacements))
            out.append(_translate_tag(match.group(0), replacements))
            pos = match.end()
        out.append(_replace_all(chunk[pos:], replacements))
    return "".join(out)
