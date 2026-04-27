from __future__ import annotations

from http.cookies import SimpleCookie
import os
import secrets
import threading
import time


AUTH_USERS_RAW = os.getenv("APP_LOGIN_USERS", "")
AUTH_USERNAME = os.getenv("APP_LOGIN_USERNAME", "")
AUTH_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "")
AUTH_COOKIE_NAME = os.getenv("APP_LOGIN_COOKIE_NAME", "llmkg_session")
AUTH_SESSION_TTL = int(os.getenv("APP_LOGIN_SESSION_TTL", "86400"))

ACTIVE_SESSIONS: dict[str, dict[str, object]] = {}
SESSION_LOCK = threading.Lock()


def load_auth_users() -> dict[str, str]:
    users: dict[str, str] = {}

    for item in str(AUTH_USERS_RAW or "").split(","):
        pair = item.strip()
        if not pair or ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        username = username.strip()
        if username:
            users[username] = password

    if AUTH_USERNAME:
        users.setdefault(AUTH_USERNAME, AUTH_PASSWORD)

    return users


AUTH_USERS = load_auth_users()


def get_user_group(username: str) -> str:
    return "admin" if username == "admin" else "user"


def validate_credentials(username: str, password: str) -> bool:
    return bool(username) and AUTH_USERS.get(username) == password


def create_session(username: str) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + AUTH_SESSION_TTL
    with SESSION_LOCK:
        ACTIVE_SESSIONS[token] = {
            "username": username,
            "group": get_user_group(username),
            "expires_at": expires_at,
        }
    return token, expires_at


def resolve_session_info(token: str | None) -> dict[str, object] | None:
    if not token:
        return None
    now = int(time.time())
    with SESSION_LOCK:
        session = ACTIVE_SESSIONS.get(token)
        if not session:
            return None
        expires_at = int(session.get("expires_at") or 0)
        if expires_at <= now:
            ACTIVE_SESSIONS.pop(token, None)
            return None
        return {
            "username": str(session.get("username") or ""),
            "group": str(session.get("group") or get_user_group(str(session.get("username") or ""))),
        }


def resolve_session(token: str | None) -> str | None:
    session = resolve_session_info(token)
    if not session:
        return None
    return str(session.get("username") or "")


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with SESSION_LOCK:
        ACTIVE_SESSIONS.pop(token, None)


def get_cookie_value(raw_cookie: str, name: str = AUTH_COOKIE_NAME) -> str | None:
    if not raw_cookie:
        return None
    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    morsel = cookie.get(name)
    return morsel.value if morsel else None


def build_session_cookie(token: str, max_age: int = AUTH_SESSION_TTL) -> str:
    return f"{AUTH_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
