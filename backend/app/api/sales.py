"""Ventas: cobro, consulta, devolución y reimpresión."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentStaff, DbSession, Owner
from app.models.audit import AuditLog
from app.models.preorders import Preorder
from app.models.sales import Order
from app.schemas.sales import LineIn, OrderOut, PaymentIn, RefundIn, SaleIn
from app.services.sales import (
    LineInput,
    PaymentInput,
    build_lines,
    pay_order,
    refund_order,
)

router = APIRouter(prefix="/sales", tags=["ventas"])


def _loaded(db: DbSession, order_id: uuid.UUID) -> Order | None:
    return db.scalars(
        select(Order)
        .options(selectinload(Order.lines), selectinload(Order.payments))
        .where(Order.id == order_id)
    ).one_or_none()


def _to_input(line: LineIn) -> LineInput:
    return LineInput(
        quantity=line.quantity,
        variant_id=line.variant_id,
        note=line.note,
        open_price_name=line.open_price_name,
        open_price_cents=line.open_price_cents,
        open_price_category_id=line.open_price_category_id,
        open_price_vat_rate=line.open_price_vat_rate,
    )


@router.post("", response_model=OrderOut, status_code=201)
def create_sale(data: SaleIn, db: DbSession, staff: CurrentStaff) -> OrderOut:
    """Registra y cobra una venta en una sola llamada.

    Es idempotente por el `id` que genera el TPV: si la respuesta se pierde en
    un corte de red y el terminal reenvía la venta, se devuelve la ya grabada
    con su mismo número de ticket en lugar de duplicarla.
    """
    if data.id is not None:
        existing = _loaded(db, data.id)
        if existing is not None:
            return OrderOut.model_validate(existing)

    order = Order(
        id=data.id or uuid.uuid4(),
        # Explícito: el valor por defecto de la columna no existe hasta el INSERT
        # y pay_order comprueba el estado antes de grabar.
        status="open",
        channel=data.channel,
        preorder_id=data.preorder_id,
        customer_nif=data.customer_nif,
        customer_name=data.customer_name,
        note=data.note,
        opened_at=datetime.now(timezone.utc),
    )
    order.lines.extend(build_lines(db, [_to_input(line) for line in data.lines]))
    db.add(order)

    pay_order(
        db,
        order,
        [
            PaymentInput(
                method=p.method,
                amount_cents=p.amount_cents,
                tendered_cents=p.tendered_cents,
            )
            for p in data.payments
        ],
        staff_id=staff.id,
        session_id=data.session_id,
    )

    if data.preorder_id:
        preorder = db.get(Preorder, data.preorder_id)
        if preorder is not None:
            preorder.status = "collected"

    return OrderOut.model_validate(order)


@router.get("/{order_id}", response_model=OrderOut)
def get_sale(order_id: uuid.UUID, db: DbSession, _: CurrentStaff) -> OrderOut:
    order = _loaded(db, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "venta no encontrada")
    return OrderOut.model_validate(order)


@router.get("", response_model=list[OrderOut])
def list_sales(
    db: DbSession,
    _: CurrentStaff,
    day: date | None = None,
    limit: int = Query(default=100, le=500),
) -> list[OrderOut]:
    """Tickets de un día, el más reciente primero."""
    stmt = (
        select(Order)
        .options(selectinload(Order.lines), selectinload(Order.payments))
        .where(Order.status != "open")
        .order_by(Order.closed_at.desc())
        .limit(limit)
    )
    if day is not None:
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end = datetime.combine(day, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(Order.closed_at.between(start, end))

    return [OrderOut.model_validate(o) for o in db.scalars(stmt).all()]


@router.post("/{order_id}/refund", response_model=OrderOut, status_code=201)
def refund_sale(
    order_id: uuid.UUID, data: RefundIn, db: DbSession, staff: Owner
) -> OrderOut:
    """Devolución total o parcial. Solo el dueño, y queda en la auditoría."""
    original = _loaded(db, order_id)
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "venta no encontrada")

    refund = refund_order(
        db,
        original,
        line_ids=data.line_ids,
        staff_id=staff.id,
        reason=data.reason,
    )
    # La devolución también se cobra: se paga en efectivo al cliente
    pay_order(
        db,
        refund,
        [PaymentInput(method="cash", amount_cents=refund.total_cents)],
        staff_id=staff.id,
    )

    db.add(
        AuditLog(
            staff_id=staff.id,
            action="refund",
            entity="order",
            entity_id=original.id,
            payload={
                "refund_order_id": str(refund.id),
                "total_cents": refund.total_cents,
                "reason": data.reason,
                "partial": bool(data.line_ids),
            },
        )
    )
    return OrderOut.model_validate(refund)


@router.post("/{order_id}/reprint", response_model=OrderOut)
def reprint(order_id: uuid.UUID, db: DbSession, staff: CurrentStaff) -> OrderOut:
    """Devuelve el ticket para imprimirlo de nuevo; la copia se marca en el TPV."""
    order = _loaded(db, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "venta no encontrada")
    db.add(
        AuditLog(
            staff_id=staff.id, action="reprint", entity="order", entity_id=order.id
        )
    )
    return OrderOut.model_validate(order)
