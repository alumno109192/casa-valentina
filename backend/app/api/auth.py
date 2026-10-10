"""Entrada al TPV con PIN de 4 dígitos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentStaff, DbSession
from app.core.config import get_settings
from app.core.security import create_token, verify_pin
from app.models.org import Staff

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    device_id: str | None = None


class LoginOut(BaseModel):
    token: str
    staff_id: str
    name: str
    role: str


class StaffOut(BaseModel):
    """Para la pantalla de entrada: nombres, nunca el hash del PIN."""

    id: str
    name: str
    role: str


# Freno a la fuerza bruta por terminal, no por usuario: bloquear al usuario
# dejaría el mostrador sin cobrar por un PIN mal teclado. Vive en memoria
# porque el backend corre en el propio local y reiniciarlo es aceptable.
_attempts: dict[str, tuple[int, datetime | None]] = {}


def _throttle_key(request: Request) -> str:
    """Clave del contador de intentos: la IP del terminal, y nada más.

    El `device_id` NO entra aquí aunque venga en la petición. Lo elige el
    cliente, así que cualquier dato suyo en la clave reabre el agujero:
    mandando un valor nuevo en cada intento, cada intento aterrizaba en una
    entrada distinta del diccionario y el contador nunca llegaba al tope, de
    modo que se podían recorrer los 10.000 PIN de cuatro dígitos.

    Contar por IP sigue siendo «por terminal» y no «por usuario», que es lo
    que persigue la decisión 8: un PIN mal teclado no deja sin cobrar al
    resto del personal.
    """
    return request.client.host if request.client else "desconocido"


def _purge_attempts(now: datetime) -> None:
    """Quita las entradas caducadas.

    El diccionario se indexa con datos que vienen de la petición; sin purga
    crece sin tope mientras el proceso viva.
    """
    expired = [
        key
        for key, (_, locked_until) in _attempts.items()
        if locked_until is not None and locked_until <= now
    ]
    for key in expired:
        del _attempts[key]


@router.get("/staff", response_model=list[StaffOut])
def list_staff(db: DbSession, _: CurrentStaff) -> list[StaffOut]:
    """Plantilla activa. Exige token: sin él, publicar el id del dueño en la
    red del local es la mitad del trabajo de quien quiera forjarse un token."""
    rows = db.scalars(select(Staff).where(Staff.active).order_by(Staff.name)).all()
    return [StaffOut(id=str(s.id), name=s.name, role=s.role) for s in rows]


@router.post("/login", response_model=LoginOut)
def login(data: LoginIn, request: Request, db: DbSession) -> LoginOut:
    """Identifica por PIN.

    En el mostrador el cajero solo teclea cuatro dígitos, sin elegir usuario
    antes, así que se busca el PIN entre el personal activo. Los PIN tienen que
    ser distintos entre sí.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    _purge_attempts(now)
    key = _throttle_key(request)

    failures, locked_until = _attempts.get(key, (0, None))
    if locked_until and locked_until > now:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "demasiados intentos, espera unos minutos",
        )

    for staff in db.scalars(select(Staff).where(Staff.active)).all():
        if verify_pin(data.pin, staff.pin_hash):
            _attempts.pop(key, None)
            return LoginOut(
                token=create_token(str(staff.id), staff.role, data.device_id),
                staff_id=str(staff.id),
                name=staff.name,
                role=staff.role,
            )

    failures += 1
    if failures >= settings.max_pin_attempts:
        _attempts[key] = (0, now + timedelta(minutes=settings.pin_lockout_minutes))
    else:
        _attempts[key] = (failures, None)

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "PIN incorrecto")


@router.get("/me", response_model=StaffOut)
def me(staff: CurrentStaff) -> StaffOut:
    return StaffOut(id=str(staff.id), name=staff.name, role=staff.role)
