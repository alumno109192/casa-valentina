"""Negocio, dispositivos y personal."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Entity, TZDateTime, one_of

STAFF_ROLES = ("owner", "cashier")


class Business(Entity):
    __tablename__ = "business"

    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str] = mapped_column(String(200))
    nif: Mapped[str] = mapped_column(String(20))
    legal_form: Mapped[str] = mapped_column(String(20))  # sociedad | autonomo
    address: Mapped[str | None] = mapped_column(String(300))
    phone_whatsapp: Mapped[str | None] = mapped_column(String(30))
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Madrid")
    ticket_footer: Mapped[str | None] = mapped_column(String(200))


class Device(Entity):
    """Un terminal. ticket_series es propia de cada dispositivo para que la
    numeración no necesite coordinarse por red (ver docs/decisiones.md)."""

    __tablename__ = "devices"

    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="pos")  # pos | admin
    ticket_series: Mapped[str | None] = mapped_column(String(10))
    is_ticket_issuer: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Staff(Entity):
    __tablename__ = "staff"
    __table_args__ = (
        CheckConstraint(one_of("role", STAFF_ROLES), name="ck_staff_role"),
    )

    name: Mapped[str] = mapped_column(String(100))
    pin_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="cashier")  # owner | cashier
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TicketCounter(Base):
    """Último número usado por serie. Una fila por serie, bloqueada al asignar,
    para que la numeración sea correlativa y sin huecos aunque haya dos
    terminales emitiendo a la vez."""

    __tablename__ = "ticket_counters"

    series: Mapped[str] = mapped_column(String(10), primary_key=True)
    last_number: Mapped[int] = mapped_column(default=0)
