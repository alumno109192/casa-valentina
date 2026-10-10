"""Ventas: cobro, consulta, devolución y reimpresión."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentStaff, DbSession, Owner
from app.core.clock import day_range
from app.models.audit import AuditLog
from app.models.preorders import Preorder
from app.models.sales import SETTLED_STATUS, Order
from app.schemas.sales import LineIn, OrderOut, RefundIn, SaleIn
from app.services.sales import (
    LineInput,
    PaymentInput,
    build_lines,
    open_cash_session_id,
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


def _metodo_dominante(order: Order) -> str:
    """Forma de pago con la que más se cobró el ticket original."""
    por_metodo: dict[str, int] = {}
    for payment in order.payments:
        por_metodo[payment.method] = (
            por_metodo.get(payment.method, 0) + payment.amount_cents
        )
    if not por_metodo:
        return "cash"
    return max(por_metodo, key=lambda metodo: por_metodo[metodo])


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
            # Solo es un reenvio si es el mismo cobro. Antes se devolvia el
            # ticket guardado sin comparar nada, asi que una venta distinta
            # con el mismo id recibia un 201 y NO se cobraba.
            esperado = sum(p.amount_cents for p in data.payments)
            if (
                existing.refunds_order_id is not None
                or existing.status == "open"
                or existing.total_cents != esperado
                or len(existing.lines) != len(data.lines)
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "ese identificador ya corresponde a otro ticket",
                )
            return OrderOut.model_validate(existing)

    if data.preorder_id is not None:
        ya_cobrado = db.scalar(
            select(Order.id).where(
                Order.preorder_id == data.preorder_id,
                Order.status.in_(SETTLED_STATUS),
            )
        )
        if ya_cobrado is not None:
            # Sin esto se podian emitir dos tickets validos del mismo encargo
            # y cobrarle dos veces al cliente.
            raise HTTPException(
                status.HTTP_409_CONFLICT, "ese encargo ya está cobrado"
            )

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

    # La sesion de caja no la elige el terminal: mandar una cerrada (o ninguna)
    # dejaba la venta fuera de todos los cierres Z, con el dinero en el cajon.
    session_id = open_cash_session_id(db)
    if data.session_id is not None and data.session_id != session_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "la caja indicada no es la que está abierta"
        )

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
        session_id=session_id,
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
    """Tickets de un día, el más reciente primero.

    El día se corta en hora local (ver core/clock.py): cortarlo en UTC metía
    los cierres de después de medianoche en la jornada anterior.
    """
    stmt = (
        select(Order)
        .options(selectinload(Order.lines), selectinload(Order.payments))
        .where(Order.status != "open")
        .order_by(Order.closed_at.desc())
        .limit(limit)
    )
    if day is not None:
        start, end = day_range(day)
        stmt = stmt.where(Order.closed_at >= start, Order.closed_at < end)

    return [OrderOut.model_validate(o) for o in db.scalars(stmt).all()]


@router.post("/{order_id}/refund", response_model=OrderOut, status_code=201)
def refund_sale(
    order_id: uuid.UUID, data: RefundIn, db: DbSession, staff: Owner
) -> OrderOut:
    """Devolución total o parcial. Solo el dueño, y queda en la auditoría."""
    original = _loaded(db, order_id)
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "venta no encontrada")

    session_id = open_cash_session_id(db)
    if session_id is None:
        # Devolver mueve dinero del cajón: sin caja abierta no hay cierre Z al
        # que imputarlo y el arqueo saldría descuadrado.
        raise HTTPException(status.HTTP_409_CONFLICT, "no hay caja abierta")

    refund = refund_order(
        db,
        original,
        line_ids=data.line_ids,
        staff_id=staff.id,
        reason=data.reason,
    )

    # Se devuelve por donde se cobró, salvo que el dueño diga otra cosa.
    # Pagar siempre en efectivo vaciaba el cajón por una comida que había
    # entrado por datáfono.
    metodo = data.method or _metodo_dominante(original)
    pay_order(
        db,
        refund,
        [PaymentInput(method=metodo, amount_cents=refund.total_cents)],
        staff_id=staff.id,
        session_id=session_id,
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
                "method": metodo,
                "original_status": original.status,
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
