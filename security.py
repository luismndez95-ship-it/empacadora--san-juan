"""Rate limiting simple, en memoria -- suficiente para una sola instancia
(ver la misma decision documentada en barberia-demo/security.py).
"""
import time
from collections import defaultdict

from fastapi import Request

_hits: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(key: str, max_hits: int, window_seconds: int) -> bool:
    now = time.time()
    window_start = now - window_seconds
    hits = [h for h in _hits[key] if h > window_start]
    hits.append(now)
    _hits[key] = hits
    return len(hits) > max_hits


_failed_logins: dict[str, list[float]] = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


def register_failed_login(key: str) -> None:
    _failed_logins[key].append(time.time())


def is_locked_out(key: str) -> bool:
    now = time.time()
    window_start = now - LOGIN_LOCKOUT_SECONDS
    attempts = [a for a in _failed_logins[key] if a > window_start]
    _failed_logins[key] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def clear_failed_logins(key: str) -> None:
    _failed_logins.pop(key, None)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
