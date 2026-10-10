"""Esquemas de ventas, caja y encargos."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Tipos de IVA que el negocio puede aplicar. Un tipo inventado en el desglose
# no lo acepta la AEAT, así que se rechaza en la frontera y no más adentro.
VAT_RATES = (0, 4, 10, 21)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Venta ------------------------------------------------------------------

class LineIn(BaseModel):
    """El TPV manda la variante elegida; el precio lo pone el servidor.

    Para precio libre se manda nombre, importe y familia.
    """

    variant_id: uuid.UUID | None = None
    # Positiva siempre: el signo negativo es exclusivo de la devolución, que
    # exige rol de dueño. Sin esta cota, una «venta» de cantidad negativa saca
    # dinero del cajón saltándose ese permiso.
    quantity: int = Field(default=1, gt=0, le=999)
    note: str | None = None
    open_price_name: str | None = None
    open_price_cents: int | None = Field(default=None, gt=0, le=1_000_000)
    open_price_category_id: uuid.UUID | None = None
    open_price_vat_rate: int | None = None

    @field_validator("open_price_vat_rate")
    @classmethod
    def _tipo_de_iva_admitido(cls, value: int | None) -> int | None:
        if value is not None and value not in VAT_RATES:
            raise ValueError(f"tipo de IVA no admitido: {value}")
        return value

    @model_validator(mode="after")
    def _variante_o_precio_libre(self):
        if self.variant_id is None and self.open_price_cents is None:
            raise ValueError("la línea necesita una variante o un importe libre")
        return self


class PaymentIn(BaseModel):
    method: Literal["cash", "card"]
    # Positivo: el reparto en negativo de una devolución lo construye el
    # servidor, nunca el terminal. Un pago negativo colado en una venta normal
    # resta del efectivo esperado del cierre sin que nada lo delate.
    amount_cents: int = Field(gt=0)
    tendered_cents: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _entregado_solo_en_efectivo(self):
        if self.method != "cash" and self.tendered_cents is not None:
            raise ValueError("lo entregado solo tiene sentido en efectivo")
        return self


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
    # min_length=1: una lista vacía es falsy y se interpretaba como «devuélvelo
    # todo», que es lo contrario de lo que pide quien manda una lista.
    line_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    reason: str | None = None
    # None = se devuelve por donde se cobró.
    method: Literal["cash", "card"] | None = None


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
    # Para que el terminal sepa en qué cierre Z ha caído la venta.
    session_id: uuid.UUID | None = None
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
    """Movimiento de caja. El signo lo pone el servidor a partir del `kind`.

    Antes el signo venía del cliente y la semántica era «positivo entra,
    negativo sale», sin nada que lo ligara al tipo: una retirada con importe
    positivo *subía* el efectivo esperado, con lo que el descuadre salía del
    doble del importe retirado.
    """

    kind: Literal["deposit_in", "deposit_out", "withdrawal", "float_in", "correction"]
    amount_cents: int = Field(gt=0)
    reason: str | None = None
    related_deposit_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _motivo_obligatorio_si_mueve_dinero_propio(self):
        if self.kind in ("withdrawal", "correction") and not (self.reason or "").strip():
            raise ValueError("una retirada o corrección necesita motivo")
        return self


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
    # Desglose de los movimientos: sin él, una retirada de 200 y cuatro fianzas
    # de 50 se anulan y el arqueo no deja ver ninguna de las dos cosas.
    deposits_in_cents: int = 0
    deposits_out_cents: int = 0
    withdrawals_cents: int = 0
    float_in_cents: int = 0
    corrections_cents: int = 0
    deposits_held_cents: int = 0
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
