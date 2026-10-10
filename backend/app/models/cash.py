"""Caja: sesiones (cierre Z), movimientos y fianzas de paellera."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, Entity, TZDateTime, one_of

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
    __table_args__ = (
        # Dos cierres con el mismo número rompen la correlatividad del libro.
        Index("uq_cash_sessions_z_number", "z_number", unique=True),
        # Una sola caja abierta a la vez, garantizado por la base y no por un
        # SELECT seguido de un INSERT. Se indexa una expresión constante
        # porque dos NULL no colisionan entre sí en un índice normal.
        Index(
            "uq_cash_sessions_abierta",
            text("(closed_at IS NULL)"),
            unique=True,
            sqlite_where=text("closed_at IS NULL"),
            postgresql_where=text("closed_at IS NULL"),
        ),
    )

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
    __table_args__ = (
        CheckConstraint(one_of("kind", MOVEMENT_KINDS), name="ck_cash_movements_kind"),
        # El signo tiene que corresponder al tipo: una retirada con importe
        # positivo inflaba el efectivo esperado del cierre.
        CheckConstraint(
            "(kind IN ('deposit_out', 'withdrawal') AND amount_cents <= 0) OR "
            "(kind IN ('deposit_in', 'float_in') AND amount_cents >= 0) OR "
            "kind = 'correction'",
            name="ck_cash_movements_signo",
        ),
    )

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
    __table_args__ = (
        CheckConstraint(one_of("status", DEPOSIT_STATUS), name="ck_deposits_status"),
    )

    item: Mapped[str] = mapped_column(String(100), default="Paellera")
    customer_name: Mapped[str | None] = mapped_column(String(150))
    customer_phone: Mapped[str | None] = mapped_column(String(30))
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="held", index=True)
    taken_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    returned_at: Mapped[datetime | None] = mapped_column(TZDateTime)
