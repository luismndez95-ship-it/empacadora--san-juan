"""Rate limiting simple, en memoria -- suficiente para una sola instancia
(ver la misma decision documentada en barberia-demo/security.py).
"""
import os
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
    # X-Forwarded-For NO sirve: su primer valor lo escribe el cliente y basta
    # con cambiarlo en cada intento para saltarse el limite. En Fly.io el proxy
    # pone Fly-Client-IP con la IP real (y pisa la que mande el cliente); solo
    # se confia en ese header cuando de verdad corremos detras de Fly.
    if os.environ.get("FLY_APP_NAME"):
        fly_ip = request.headers.get("fly-client-ip", "").strip()
        if fly_ip:
            return fly_ip
    return request.client.host if request.client else "unknown"
