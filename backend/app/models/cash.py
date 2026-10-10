"""Caja: sesiones (cierre Z), movimientos y fianzas de paellera."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, Entity, TZDateTime

MOVEMENT_KINDS = (
    "deposit_in",    # entra una fianza de paellera
    "deposit_out",   # se devuelve la fianza
    "withdrawal",    # retirada de efectivo
    "float_in",      # aportación al cambio
    "correction",
)
DEPOSIT_STATUS = ("held", "returned", "kept")


class CashSession(Entity):
    __tablename__ = "cash_sessions"

    device_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("devices.id"))
    z_number: Mapped[int | None] = mapped_column(Integer)

    opened_by: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("staff.id"))
    opened_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    opening_float_cents: Mapped[int] = mapped_column(Integer, default=0)

    closed_by: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("staff.id"))
    closed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    counted_cash_cents: Mapped[int | None] = mapped_column(Integer)
    expected_cash_cents: Mapped[int | None] = mapped_column(Integer)
    # Lo que el cajero marcó como tarjeta en el TPV. Sin integración con el
    # datáfono esto NO está conciliado con el banco: el informe Z lo advierte.
    card_total_cents: Mapped[int | None] = mapped_column(Integer)
    difference_cents: Mapped[int | None] = mapped_column(Integer)
    close_note: Mapped[str | None] = mapped_column(String(500))


class CashMovement(Entity):
    __tablename__ = "cash_movements"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("cash_sessions.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    amount_cents: Mapped[int] = mapped_column(Integer)  # positivo entra, negativo sale
    reason: Mapped[str | None] = mapped_column(String(300))
    related_deposit_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("deposits.id")
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("staff.id"))


class Deposit(Entity):
    """Fianza de paellera. No es una venta y no lleva IVA: queda fuera del
    ticket y solo mueve caja. Pendiente de confirmar con la gestoría."""

    __tablename__ = "deposits"

    item: Mapped[str] = mapped_column(String(100), default="Paellera")
    customer_name: Mapped[str | None] = mapped_column(String(150))
    customer_phone: Mapped[str | None] = mapped_column(String(30))
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="held", index=True)
    taken_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    returned_at: Mapped[datetime | None] = mapped_column(TZDateTime)
