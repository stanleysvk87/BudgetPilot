#!/usr/bin/env python3
"""Small HTTP helpers shared by every module that registers routes.

`budgetpilot_web.py`, `envelope_editor.py` and `balance_first_summary.py`
all redirect back to "wherever the action was submitted from". Doing that
from a raw `request.referrer` is an open redirect: the referrer is
attacker-influenced and may point at another origin entirely. The rule the
codebase follows is to keep only the local path — this module is where
that rule lives, so a route can't accidentally skip it (which is exactly
what happened in envelope_editor.py and balance_first_summary.py, the two
route modules that couldn't import the helper out of budgetpilot_web
without a circular import).
"""
from __future__ import annotations

from urllib.parse import urlparse

from flask import redirect, request


def safe_local_path(value, default: str = "/") -> str:
    """`value` reduced to a same-origin path (+ query), or `default`.

    Anything with a scheme or host, and anything not starting with "/",
    is discarded rather than followed.
    """
    parsed = urlparse(value or "")
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return default
    return parsed.path + (("?" + parsed.query) if parsed.query else "")


def redirect_back(default: str = "/"):
    """Redirect to the referring page, never off-site."""
    return redirect(safe_local_path(request.referrer, default))
