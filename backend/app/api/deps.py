"""Dependencias comunes: sesión de BD y usuario autenticado."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token
from app.models.org import Staff

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


def current_staff(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> Staff:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "falta el token")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sesión caducada")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token inválido")

    staff = db.get(Staff, uuid.UUID(payload["sub"]))
    if staff is None or not staff.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "usuario no válido")
    return staff


CurrentStaff = Annotated[Staff, Depends(current_staff)]


def require_owner(staff: CurrentStaff) -> Staff:
    """Anulaciones, cambios de precio y apertura de cajón sin venta."""
    if staff.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requiere permisos de dueño")
    return staff


Owner = Annotated[Staff, Depends(require_owner)]
