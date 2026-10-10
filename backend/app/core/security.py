"""PIN del personal y tokens del TPV.

Se usa bcrypt directamente, no passlib: passlib 1.7 está sin mantenimiento y
rompe con bcrypt >= 4.1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


def hash_pin(pin: str) -> str:
    if not pin.isdigit() or len(pin) != 4:
        raise ValueError("el PIN debe tener 4 dígitos")
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), pin_hash.encode())
    except ValueError:
        return False


def create_token(subject: str, role: str, device_id: str | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "device": device_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Valida firma y reclamaciones obligatorias.

    `require` no es decorativo: sin él, PyJWT acepta un token sin `exp`, que
    nunca caduca. Un token forjado sería eterno.
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
