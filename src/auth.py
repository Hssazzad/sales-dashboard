"""Single-admin authentication for the Streamlit dashboard.

HOW SESSION RESTORE WORKS (after a browser refresh / F5)
--------------------------------------------------------
* On login we create a random token, store only its SHA-256 hash in the
  ``dashboard_session`` table, and write the raw token into a browser cookie.
* On a refresh Streamlit starts a brand-new session (``st.session_state`` is
  empty).  The browser sends its cookies with the websocket handshake, and
  ``st.context.cookies`` exposes them to Python on the very FIRST script run,
  so no JavaScript round-trip or "loading" run is needed to READ the cookie.
* Only WRITING / REMOVING the cookie needs JavaScript (the
  streamlit-cookies-controller component).  That component is a hidden iframe
  which must stay on screen long enough to run its JS.  If we call
  ``st.rerun()`` immediately, the iframe is removed before it executes and the
  cookie is never written.  That was the cause of the "login page again after
  refresh" bug, so we wait briefly before rerunning.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
import hmac
import secrets

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from streamlit_cookies_controller import CookieController

from src.db import get_engine


_HASH_ITERATIONS = 310_000
_SESSION_COOKIE = "sales_dashboard_session"
_SESSION_DAYS = 7

# Internal session-state / widget keys — never exposed to the user.
_AUTHENTICATED_KEY = "authenticated"
_COOKIE_WRITER_KEY = "auth_cookie_writer"

# How long to keep the hidden cookie iframe on screen before st.rerun(), so its
# JavaScript can actually write / remove the browser cookie.
_COOKIE_WRITE_WAIT_SECONDS = 1.0

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level helpers — DB and crypto, no Streamlit calls
# ---------------------------------------------------------------------------

def _normalise_phone(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


def _password_hash(password: str, salt: bytes) -> str:
    return pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS
    ).hex()


def _ensure_auth_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS dashboard_auth (
                id            TINYINT      NOT NULL PRIMARY KEY,
                phone         VARCHAR(20)  NOT NULL,
                password_salt CHAR(32)     NOT NULL,
                password_hash CHAR(64)     NOT NULL
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS dashboard_session (
                token_hash CHAR(64) NOT NULL PRIMARY KEY,
                expires_at DATETIME NOT NULL
            )
            """
        ))


def _is_configured() -> bool:
    _ensure_auth_table()
    with get_engine().connect() as conn:
        return conn.execute(
            text("SELECT 1 FROM dashboard_auth WHERE id = 1")
        ).first() is not None


def _create_admin(phone: str, password: str) -> bool:
    _ensure_auth_table()
    salt = secrets.token_bytes(16)
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO dashboard_auth (id, phone, password_salt, password_hash)
                    VALUES (1, :phone, :salt, :hash)
                    """
                ),
                {
                    "phone": _normalise_phone(phone),
                    "salt":  salt.hex(),
                    "hash":  _password_hash(password, salt),
                },
            )
    except IntegrityError:
        return False
    return True


def _authenticate(phone: str, password: str) -> bool:
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT password_salt, password_hash
                FROM dashboard_auth
                WHERE id = 1 AND phone = :phone
                """
            ),
            {"phone": _normalise_phone(phone)},
        ).mappings().first()

    if row is None:
        return False

    computed = _password_hash(password, bytes.fromhex(row["password_salt"]))
    return hmac.compare_digest(computed, row["password_hash"])


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _create_session() -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=_SESSION_DAYS)
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dashboard_session (token_hash, expires_at)
                VALUES (:token_hash, :expires_at)
                """
            ),
            {"token_hash": _token_hash(token), "expires_at": expires_at},
        )
    _log.info("[auth] DB session created (hash prefix: %s...)", _token_hash(token)[:8])
    return token


def _session_is_valid(token: str | None) -> bool:
    if not token:
        _log.info("[auth] _session_is_valid: no token")
        return False
    h = _token_hash(token)
    _log.info("[auth] Validating token (hash prefix: %s...)", h[:8])
    with get_engine().connect() as conn:
        ok = conn.execute(
            text(
                """
                SELECT 1 FROM dashboard_session
                WHERE token_hash = :h AND expires_at > :now
                """
            ),
            {"h": h, "now": datetime.now(timezone.utc).replace(tzinfo=None)},
        ).first() is not None
    _log.info("[auth] DB token valid: %s", ok)
    return ok


def _delete_session(token: str | None) -> None:
    if not token:
        return
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM dashboard_session WHERE token_hash = :h"),
            {"h": _token_hash(token)},
        )
    _log.info("[auth] DB session deleted")


def _current_phone() -> str:
    with get_engine().connect() as conn:
        return str(conn.execute(
            text("SELECT phone FROM dashboard_auth WHERE id = 1")
        ).scalar_one())


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def _browser_session_token() -> str | None:
    """Read the session cookie server-side from the browser's request headers.

    ``st.context.cookies`` is a snapshot taken when the browser connected, so it
    is available on the first script run after a refresh.  It does NOT change
    when we set/remove a cookie later in the same browser session; in-session
    state is tracked with ``st.session_state`` instead.
    """
    try:
        return st.context.cookies.get(_SESSION_COOKIE)
    except Exception:  # very old Streamlit without st.context.cookies
        _log.exception("[auth] st.context.cookies is unavailable")
        return None


def _write_session_cookie(token: str) -> None:
    """Ask the browser to store the session cookie.

    The caller MUST keep the script alive for a moment afterwards (see
    ``_COOKIE_WRITE_WAIT_SECONDS``) before calling ``st.rerun()``.
    """
    CookieController(key=_COOKIE_WRITER_KEY).set(
        _SESSION_COOKIE,
        token,
        max_age=_SESSION_DAYS * 24 * 60 * 60,
        same_site="strict",
    )


def _remove_session_cookie() -> None:
    """Ask the browser to delete the session cookie (see note above)."""
    try:
        CookieController(key=_COOKIE_WRITER_KEY).remove(
            _SESSION_COOKIE, same_site="strict"
        )
    except KeyError:
        # The library pops the name from its local dict AFTER it has already
        # sent the "remove" command to the browser, and that dict is empty
        # here, so this KeyError is harmless.
        pass


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _render_auth_style() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
          display: none;
        }
        [data-testid="stMainBlockContainer"] { padding-top: 18vh; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          background: var(--secondary-background-color);
          border-color: var(--border-color);
          border-radius: .75rem;
          box-shadow: 0 12px 30px rgba(0, 0, 0, .18);
        }
        div[data-testid="stForm"] { border: 0; padding: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _valid_phone(phone: str) -> bool:
    return 8 <= len(_normalise_phone(phone)) <= 15


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def require_login() -> None:
    """Show initial setup or login and stop unauthenticated page rendering."""
    # Fast path: already authenticated in this browser session.
    if st.session_state.get(_AUTHENTICATED_KEY):
        _log.info("[auth] Already authenticated (session_state)")
        return

    # Refresh path: try to restore the session from the browser cookie.
    try:
        cookie_names = list(st.context.cookies.keys())
    except Exception:
        cookie_names = []
    token = _browser_session_token()
    _log.info(
        "[auth] Fresh session — cookies seen: %s  session cookie present: %s",
        cookie_names,
        token is not None,
    )

    try:
        if _session_is_valid(token):
            _log.info("[auth] Session restored from cookie")
            st.session_state[_AUTHENTICATED_KEY] = True
            return
    except Exception:
        st.error("Authentication service is unavailable. Check the database connection.")
        st.stop()

    _log.info("[auth] No valid session — showing login form")
    _render_auth_style()

    try:
        configured = _is_configured()
    except Exception:
        st.error("Authentication service is unavailable. Check the database connection.")
        st.stop()

    _, col, _ = st.columns(3)
    with col:
        with st.container(border=True):
            if configured:
                st.subheader("Sign in")
                st.caption("Enter your phone number and password to continue.")
                with st.form("login_form", border=False):
                    phone    = st.text_input("Phone number", placeholder="01XXXXXXXXX")
                    password = st.text_input("Password", type="password")
                    submitted = st.form_submit_button("Sign in", width="stretch")

                if submitted:
                    if _authenticate(phone, password):
                        _log.info("[auth] Login succeeded — writing cookie")
                        new_token = _create_session()
                        _write_session_cookie(new_token)
                        st.session_state[_AUTHENTICATED_KEY] = True
                        # IMPORTANT: give the hidden cookie iframe time to run
                        # its JS before the rerun removes it from the page.
                        time.sleep(_COOKIE_WRITE_WAIT_SECONDS)
                        _log.info("[auth] Authenticated — rerunning")
                        st.rerun()
                    st.error("Incorrect phone number or password.")
            else:
                st.subheader("Set password")
                st.caption("Set the administrator phone number and password once.")
                with st.form("initial_setup_form", border=False):
                    phone            = st.text_input("Phone number", placeholder="01XXXXXXXXX")
                    password         = st.text_input("Password", type="password")
                    confirm_password = st.text_input("Confirm password", type="password")
                    submitted        = st.form_submit_button("Set password", width="stretch")

                if submitted:
                    if not _valid_phone(phone):
                        st.error("Enter a valid phone number.")
                    elif len(password) < 8:
                        st.error("Password must be at least 8 characters long.")
                    elif password != confirm_password:
                        st.error("Passwords do not match.")
                    elif _create_admin(phone, password):
                        st.success("Password set. Please sign in.")
                        st.rerun()
                    else:
                        st.error("The account has already been configured. Refresh the page.")

    st.stop()


def render_profile() -> None:
    """Show the signed-in account and logout button in the sidebar."""
    with st.sidebar:
        st.divider()
        st.caption("PROFILE")
        try:
            st.write(_current_phone())
        except Exception:
            st.write("Signed-in user")

        if st.button("Log out", key="logout", width="stretch"):
            _log.info("[auth] Logout — deleting DB session and cookie")
            # The cookie snapshot from the browser connection still holds the
            # token, which is what we need to invalidate it in the database.
            # Even if the browser cookie lingers, the DB row is gone, so it can
            # no longer restore a session.
            try:
                _delete_session(_browser_session_token())
            except Exception:
                _log.exception("[auth] Could not delete DB session on logout")
            _remove_session_cookie()
            st.session_state.pop(_AUTHENTICATED_KEY, None)
            # Let the hidden iframe remove the browser cookie before rerunning.
            time.sleep(_COOKIE_WRITE_WAIT_SECONDS)
            st.rerun()