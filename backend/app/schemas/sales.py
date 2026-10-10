"""Esquemas de ventas, caja y encargos."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Venta ------------------------------------------------------------------

class LineIn(BaseModel):
    """El TPV manda la variante elegida; el precio lo pone el servidor.

    Para precio libre se manda nombre, importe y familia.
    """

    variant_id: uuid.UUID | None = None
    quantity: int = 1
    note: str | None = None
    open_price_name: str | None = None
    open_price_cents: int | None = Field(default=None, ge=0)
    open_price_category_id: uuid.UUID | None = None
    open_price_vat_rate: int | None = None

    @model_validator(mode="after")
    def _variante_o_precio_libre(self):
        if self.variant_id is None and self.open_price_cents is None:
            raise ValueError("la línea necesita una variante o un importe libre")
        if self.quantity == 0:
            raise ValueError("la cantidad no puede ser cero")
        return self


class PaymentIn(BaseModel):
    method: Literal["cash", "card"]
    amount_cents: int
    tendered_cents: int | None = Field(default=None, ge=0)


class SaleIn(BaseModel):
    """Una venta completa: líneas y cobro en una sola llamada.

    El TPV genera el `id` para que reenviar la misma venta tras un corte de red
    no la duplique (idempotencia).
    """

    id: uuid.UUID | None = None
    lines: list[LineIn] = Field(min_length=1)
    payments: list[PaymentIn] = Field(min_length=1)
    channel: Literal["counter", "phone", "whatsapp", "menu_online"] = "counter"
    preorder_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    customer_nif: str | None = None
    customer_name: str | None = None
    note: str | None = None


class RefundIn(BaseModel):
    line_ids: list[uuid.UUID] | None = None
    reason: str | None = None


class VatGroupOut(BaseModel):
    rate: int
    gross_cents: int
    base_cents: int
    vat_cents: int


class LineOut(ORMModel):
    id: uuid.UUID
    name_snapshot: str
    unit_price_cents: int
    quantity: int
    vat_rate: int
    line_total_cents: int
    note: str | None = None


class PaymentOut(ORMModel):
    id: uuid.UUID
    method: str
    amount_cents: int
    tendered_cents: int | None = None
    change_cents: int | None = None


class OrderOut(ORMModel):
    id: uuid.UUID
    status: str
    channel: str
    ticket_full_number: str | None = None
    total_cents: int
    base_cents: int
    vat_cents: int
    vat_breakdown: list[VatGroupOut] | None = None
    customer_nif: str | None = None
    customer_name: str | None = None
    refunds_order_id: uuid.UUID | None = None
    note: str | None = None
    closed_at: datetime | None = None
    lines: list[LineOut] = []
    payments: list[PaymentOut] = []


# --- Caja -------------------------------------------------------------------

class SessionOpenIn(BaseModel):
    opening_float_cents: int = Field(default=0, ge=0)
    device_id: uuid.UUID | None = None


class SessionCloseIn(BaseModel):
    counted_cash_cents: int = Field(ge=0)
    close_note: str | None = None


class MovementIn(BaseModel):
    kind: Literal["deposit_in", "deposit_out", "withdrawal", "float_in", "correction"]
    amount_cents: int
    reason: str | None = None
    related_deposit_id: uuid.UUID | None = None


class SessionOut(ORMModel):
    id: uuid.UUID
    z_number: int | None = None
    opened_at: datetime | None = None
    opening_float_cents: int
    closed_at: datetime | None = None
    counted_cash_cents: int | None = None
    expected_cash_cents: int | None = None
    card_total_cents: int | None = None
    difference_cents: int | None = None
    close_note: str | None = None


class ZReport(BaseModel):
    """Informe de cierre. `card_reconciled` es siempre falso mientras el
    datáfono no esté integrado: el total de tarjeta es lo que marcó el cajero,
    no lo que liquidó el banco."""

    session: SessionOut
    ticket_count: int
    sales_total_cents: int
    cash_sales_cents: int
    card_sales_cents: int
    movements_cents: int
    expected_cash_cents: int
    counted_cash_cents: int | None = None
    difference_cents: int | None = None
    vat_breakdown: list[VatGroupOut] = []
    card_reconciled: bool = False


# --- Encargos ---------------------------------------------------------------

class PreorderLineIn(BaseModel):
    variant_id: uuid.UUID | None = None
    name_snapshot: str | None = None
    quantity: int = Field(default=1, gt=0)
    note: str | None = None


class PreorderLineOut(ORMModel):
    id: uuid.UUID
    variant_id: uuid.UUID | None = None
    name_snapshot: str
    quantity: int
    note: str | None = None


class PreorderIn(BaseModel):
    customer_name: str = Field(min_length=1, max_length=150)
    customer_phone: str | None = None
    pickup_date: date
    pickup_time: time
    channel: Literal["phone", "whatsapp", "counter", "menu_online"] = "phone"
    notes: str | None = None
    lines: list[PreorderLineIn] = Field(min_length=1)


class PreorderOut(ORMModel):
    id: uuid.UUID
    customer_name: str
    customer_phone: str | None = None
    pickup_date: date
    pickup_time: time
    status: str
    channel: str
    notes: str | None = None
    lines: list[PreorderLineOut] = []


class PreorderStatusIn(BaseModel):
    status: Literal["pending", "ready", "collected", "cancelled", "no_show"]
