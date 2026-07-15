#!/usr/bin/env python3
"""Shared test-client helper for CSRF-protected routes.

budgetpilot_web.py's require_csrf_token() before_request hook rejects any
non-GET/HEAD/OPTIONS request that doesn't carry a csrf_token matching the
current session's token (see docs on that function). Real browsers get
this for free from the hidden <input name="csrf_token"> every POST form
now renders; existing tests posting plain dicts don't have one.

Rather than editing every individual self.client.post(..., data={...})
call across the test suite to add a token, CsrfAutoClient transparently
seeds a known token into the test client's session and attaches it to
every POST -- the same round trip a real form does, just with a fixed
token instead of a freshly rendered one.
"""
from flask.testing import FlaskClient

CSRF_TEST_TOKEN = "test-csrf-token"


class CsrfAutoClient(FlaskClient):
    def post(self, *args, **kwargs):
        with self.session_transaction() as sess:
            sess["_csrf_token"] = CSRF_TEST_TOKEN

        data = kwargs.get("data")
        if data is None:
            kwargs["data"] = {"csrf_token": CSRF_TEST_TOKEN}
        elif isinstance(data, dict) and "csrf_token" not in data:
            data = dict(data)
            data["csrf_token"] = CSRF_TEST_TOKEN
            kwargs["data"] = data
        return super().post(*args, **kwargs)


def install(app):
    """Point `app`'s test_client_class at CsrfAutoClient and return the
    previous value. Call before app.test_client() so every client it
    creates inherits the behavior above -- mirrors how budgetpilot_web.py
    registers everything on one shared Flask `app` object.

    `app` (budgetpilot_web.app) is a single module-level object shared by
    the whole test suite, so this mutation must be undone once the test
    is done, or it leaks into every test file that runs afterward in the
    same process (discovered the hard way: test_csrf_protection.py's
    real-mechanism tests started failing only when run after a test file
    that had called install() and never restored it). Callers are
    expected to restore the returned value via addCleanup, e.g.:

        previous = csrf_test_support.install(web.app)
        self.addCleanup(setattr, web.app, "test_client_class", previous)
    """
    previous = app.test_client_class
    app.test_client_class = CsrfAutoClient
    return previous
