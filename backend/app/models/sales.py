"""Ventas: pedidos, líneas y pagos.

Nada se borra: un pedido cobrado es inmutable y se corrige con una devolución
que apunta al original (`refunds_order_id`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Entity, JSONType, TZDateTime, one_of

# `partially_refunded`: el ticket tiene alguna línea devuelta pero no todas.
# Sin este estado, devolver una línea de un ticket de dos marcaba el ticket
# entero como devuelto y se perdía la pista de lo que quedaba pendiente.
ORDER_STATUS = ("open", "paid", "partially_refunded", "refunded", "voided")

# Estados en los que un ticket cuenta como cobrado para los informes y la caja.
SETTLED_STATUS = ("paid", "partially_refunded", "refunded")
CHANNELS = ("counter", "phone", "whatsapp", "menu_online")
PAYMENT_METHODS = ("cash", "card")


class Order(Entity):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("ticket_series", "ticket_number", name="uq_ticket_number"),
        CheckConstraint(one_of("status", ORDER_STATUS), name="ck_orders_status"),
        CheckConstraint(one_of("channel", CHANNELS), name="ck_orders_channel"),
        # Un ticket cobrado sin número es una factura sin numerar.
        CheckConstraint(
            "status = 'open' OR "
            "(ticket_series IS NOT NULL AND ticket_number IS NOT NULL)",
            name="ck_orders_numerado",
        ),
        # Es por lo que filtra el cierre Z.
        Index("ix_orders_session_status", "session_id", "status"),
        Index("ix_orders_refunds_order_id", "refunds_order_id"),
        # El número impreso identifica el ticket de cara al cliente.
        Index("uq_orders_ticket_full_number", "ticket_full_number", unique=True),
    )

    device_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("devices.id"))
    staff_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("staff.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("cash_sessions.id")
    )
    preorder_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("preorders.id"))

    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    channel: Mapped[str] = mapped_column(String(20), default="counter")

    # Numeración del ticket: se asigna al cobrar, correlativa por serie y sin huecos
    ticket_series: Mapped[str | None] = mapped_column(String(10))
    ticket_number: Mapped[int | None] = mapped_column(Integer)
    ticket_full_number: Mapped[str | None] = mapped_column(String(40))

    # Totales en céntimos. base + vat == total, siempre (ver core/money.py)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    base_cents: Mapped[int] = mapped_column(Integer, default=0)
    vat_cents: Mapped[int] = mapped_column(Integer, default=0)
    vat_breakdown: Mapped[list | None] = mapped_column(JSONType)

    # Datos del cliente, solo si pide factura con sus datos
    customer_nif: Mapped[str | None] = mapped_column(String(20))
    customer_name: Mapped[str | None] = mapped_column(String(200))

    refunds_order_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("orders.id"))
    note: Mapped[str | None] = mapped_column(String(500))

    opened_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(TZDateTime, index=True)

    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderLine(Entity):
    """name_snapshot, unit_price_cents y vat_rate se copian aquí: si mañana
    cambia el precio o el nombre, el ticket de ayer no cambia."""

    __tablename__ = "order_lines"
    __table_args__ = (
        # Cero unidades no es una línea; el negativo es la devolución.
        CheckConstraint("quantity <> 0", name="ck_order_lines_cantidad"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("products.id"))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("product_variants.id")
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("categories.id"))

    # Línea del ticket original que esta línea devuelve. Es lo que permite
    # rechazar la segunda devolución de la misma línea.
    refunds_line_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("order_lines.id"), index=True
    )

    name_snapshot: Mapped[str] = mapped_column(String(190))
    unit_price_cents: Mapped[int] = mapped_column(Integer)  # con IVA incluido
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    vat_rate: Mapped[int] = mapped_column(Integer, default=10)
    line_total_cents: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    order: Mapped[Order] = relationship(
        back_populates="lines", foreign_keys=[order_id]
    )


class Payment(Entity):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(one_of("method", PAYMENT_METHODS), name="ck_payments_method"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(20))  # cash | card
    amount_cents: Mapped[int] = mapped_column(Integer)
    tendered_cents: Mapped[int | None] = mapped_column(Integer)
    change_cents: Mapped[int | None] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="payments")
