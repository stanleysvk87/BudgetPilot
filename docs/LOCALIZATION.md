# Localization

BudgetPilot currently supports Slovak and English in the web UI.

## Runtime behavior

- Slovak (`sk`) is the source language and fallback language.
- English (`en`) is provided through JSON catalogs in `translations/`.
- The selected language is stored in the `budgetpilot_lang` browser cookie
  and mirrored into the Flask session when available.
- The language switcher is visible on authentication, first-run setup, and
  the main application shell.
- Missing translations fall back to Slovak source text instead of breaking
  the page.

The helper lives in `i18n.py`. It intentionally has no external dependency.
Source strings are the translation keys so existing templates and inline
messages can be localized without introducing Babel or a database.

## Files

- `i18n.py` - catalog loading, language normalization, fallback lookup, and
  rendered HTML localization.
- `translations/sk.json` - Slovak source catalog.
- `translations/en.json` - English catalog with matching keys.
- `tests/test_localization.py` - catalog parity, fallback, language-cookie,
  and rendered-page tests.

## Adding Another Language

1. Copy `translations/sk.json` to `translations/<lang>.json`.
2. Translate every value naturally for the target language. Keep the keys
   unchanged.
3. Add the language code and display name to `SUPPORTED_LANGUAGES` in
   `i18n.py`.
4. Run `python3 -m unittest tests.test_localization`.
5. Run `python3 -m unittest discover -s tests`.
6. Run `npm run test:e2e` and `npm run review:chromium`.
7. Check the language switcher in Chromium and verify no mixed-language UI
   appears on login, setup, dashboard, payments, expenses, envelopes, manage,
   problems, and debug pages.

Use normal financial terminology in the target language. Do not translate
user-entered payment names, envelope names, notes, merchant names, or runtime
data stored in JSON files.

## Known Limits

Currency formatting still uses euro formatting across languages. Date inputs
remain ISO/browser-native. These are acceptable for the first bilingual public
release because the app stores and calculates local household euro values.
