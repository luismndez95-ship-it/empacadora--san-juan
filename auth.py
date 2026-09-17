"""Hash/verificacion de contraseñas de admin, sin dependencias nativas
(nada de bcrypt/argon2 que a veces da guerra con wheels en Windows).

PBKDF2-HMAC-SHA256 con 260k iteraciones es el algoritmo que Django usa
por defecto -- sobradamente seguro para un puñado de admins, y viene
en la libreria estandar de Python (hashlib), cero instalacion extra.
"""
import hashlib
import hmac
import secrets

from fastapi import Request

_ITERATIONS = 260_000


def is_admin(request: Request) -> bool:
    return request.session.get("admin_ok") is True


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)
