"""Base declarativa y tipos portables entre SQLite (dev) y PostgreSQL (prod)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CHAR, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator


class GUID(TypeDecorator):
    """UUID nativo en PostgreSQL, CHAR(36) en SQLite."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


# jsonb en PostgreSQL, JSON de texto en SQLite
JSONType = JSON().with_variant(JSONB(), "postgresql")

TZDateTime = DateTime(timezone=True)


def one_of(column: str, values: tuple[str, ...]) -> str:
    """Cláusula `col IN (...)` para un CHECK, a partir de la tupla de estados.

    Así la lista de valores admitidos vive en un solo sitio: la tupla que ya
    documenta el modelo, en lugar de duplicarse en el CHECK.
    """
    opciones = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({opciones})"


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Entity(Base):
    """Toda tabla lleva id uuid, created_at y updated_at.

    El id se genera en el cliente (el TPV) para que la sincronización sea
    idempotente: reenviar la misma venta no la duplica.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, nullable=False, default=utcnow, onupdate=utcnow,
        server_default=func.now(),
    )


Str = String
