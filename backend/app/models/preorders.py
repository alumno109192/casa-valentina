"""Encargos por teléfono, WhatsApp o mostrador."""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Entity, one_of

PREORDER_STATUS = ("pending", "ready", "collected", "cancelled", "no_show")


class Preorder(Entity):
    __tablename__ = "preorders"
    __table_args__ = (
        CheckConstraint(one_of("status", PREORDER_STATUS), name="ck_preorders_status"),
    )

    customer_name: Mapped[str] = mapped_column(String(150))
    customer_phone: Mapped[str | None] = mapped_column(String(30))
    pickup_date: Mapped[date] = mapped_column(Date, index=True)
    pickup_time: Mapped[time] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    channel: Mapped[str] = mapped_column(String(20), default="phone")
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("staff.id"))

    lines: Mapped[list["PreorderLine"]] = relationship(
        back_populates="preorder", cascade="all, delete-orphan"
    )


class PreorderLine(Entity):
    __tablename__ = "preorder_lines"

    preorder_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("preorders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("products.id"))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("product_variants.id")
    )
    name_snapshot: Mapped[str] = mapped_column(String(190))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str | None] = mapped_column(String(300))

    preorder: Mapped[Preorder] = relationship(back_populates="lines")
