"""Alta y cobro de ventas.

Reglas que el servicio garantiza:
  * los importes de la línea se copian del catálogo en el momento de la venta;
  * base + cuota == total, agrupando el IVA por tipo (ver core/money.py);
  * un pedido cobrado no se modifica: se corrige con una devolución;
  * el número de ticket se asigna al cobrar, nunca al abrir el pedido.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.money import compute_totals
from app.models.cash import CashSession
from app.models.catalog import Product, ProductVariant
from app.models.sales import Order, OrderLine, Payment
from app.services.tickets import format_ticket_number, next_ticket_number


@dataclass
class LineInput:
    """Una línea tal y como la manda el TPV."""

    quantity: int = 1
    variant_id: uuid.UUID | None = None
    note: str | None = None
    # Solo para precio libre (sustituye al botón "PRODUCTO" de Dish)
    open_price_name: str | None = None
    open_price_cents: int | None = None
    open_price_category_id: uuid.UUID | None = None
    open_price_vat_rate: int | None = None


@dataclass
class PaymentInput:
    method: str  # cash | card
    amount_cents: int
    tendered_cents: int | None = None


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail)


def build_lines(db: Session, inputs: list[LineInput]) -> list[OrderLine]:
    """Convierte la petición del TPV en líneas con precio y nombre congelados."""
    if not inputs:
        raise _bad_request("el pedido no tiene líneas")

    lines: list[OrderLine] = []
    for position, item in enumerate(inputs):
        if item.quantity <= 0:
            # El signo negativo pertenece solo a refund_order, que exige dueno.
            raise _bad_request("la cantidad tiene que ser positiva")

        if item.variant_id is not None:
            variant = db.scalars(
                select(ProductVariant)
                .options(selectinload(ProductVariant.product))
                .where(ProductVariant.id == item.variant_id)
            ).one_or_none()
            if variant is None:
                raise _bad_request(f"la variante {item.variant_id} no existe")

            product: Product = variant.product
            if variant.archived or product.archived:
                raise _bad_request(f"{product.name} ya no esta en la carta")
            if not product.is_available:
                raise _bad_request(f"{product.name} esta agotado")
            # En un producto de precio libre el importe lo teclea el cajero
            if product.is_open_price:
                if item.open_price_cents is None:
                    raise _bad_request(
                        f"{product.name} necesita que se teclee el importe"
                    )
                unit_price = item.open_price_cents
            else:
                unit_price = variant.price_cents

            name = (
                product.name
                if variant.is_default
                else f"{product.name} ({variant.name})"
            )
            lines.append(
                OrderLine(
                    product_id=product.id,
                    variant_id=variant.id,
                    category_id=product.category_id,
                    name_snapshot=name,
                    unit_price_cents=unit_price,
                    quantity=item.quantity,
                    vat_rate=product.vat_rate,
                    line_total_cents=unit_price * item.quantity,
                    note=item.note,
                    sort_order=position,
                )
            )
            continue

        # Línea de precio libre sin producto de catálogo
        if item.open_price_cents is None or not item.open_price_name:
            raise _bad_request("la línea libre necesita nombre e importe")
        if item.open_price_category_id is None:
            raise _bad_request(
                "la línea libre necesita una familia para contar en los informes"
            )
        lines.append(
            OrderLine(
                category_id=item.open_price_category_id,
                name_snapshot=item.open_price_name,
                unit_price_cents=item.open_price_cents,
                quantity=item.quantity,
                # `is None`, no `or`: un 0 % legitimo es falsy y se
                # convertia en el 10 % por defecto sin avisar.
                vat_rate=(
                    item.open_price_vat_rate
                    if item.open_price_vat_rate is not None
                    else get_settings().default_vat_rate
                ),
                line_total_cents=item.open_price_cents * item.quantity,
                note=item.note,
                sort_order=position,
            )
        )
    return lines


def apply_totals(order: Order) -> Order:
    """Recalcula total, base, cuota y desglose a partir de las líneas."""
    totals = compute_totals(
        [(line.line_total_cents, line.vat_rate) for line in order.lines]
    )
    order.total_cents = totals.total_cents
    order.base_cents = totals.base_cents
    order.vat_cents = totals.vat_cents
    order.vat_breakdown = [
        {
            "rate": group.rate,
            "gross_cents": group.gross_cents,
            "base_cents": group.base_cents,
            "vat_cents": group.vat_cents,
        }
        for group in totals.groups
    ]
    return order


def open_cash_session_id(db: Session) -> uuid.UUID | None:
    """Id de la caja abierta, si hay alguna.

    Vive aqui para que la venta pueda atarse a la caja sin que el terminal
    tenga que decir a cual: si lo dice el cliente, puede mandar una cerrada o
    ninguna, y entonces el dinero no sale en ningun cierre Z.
    """
    return db.scalar(
        select(CashSession.id)
        .where(CashSession.closed_at.is_(None))
        .order_by(CashSession.opened_at.desc())
        .limit(1)
    )


def pay_order(
    db: Session,
    order: Order,
    payments: list[PaymentInput],
    *,
    series: str | None = None,
    staff_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> Order:
    """Cobra el pedido: valida los pagos, asigna número de ticket y lo cierra.

    Admite pago mixto (varias filas en `payments`). El cambio se calcula solo
    sobre el efectivo entregado.
    """
    if order.status != "open":
        raise _bad_request(f"el pedido ya está en estado {order.status}")
    if not payments:
        raise _bad_request("no hay pagos")

    apply_totals(order)

    es_devolucion = order.refunds_order_id is not None
    if not es_devolucion and order.total_cents <= 0:
        # Un ticket de 0 EUR o negativo que no es devolucion gasta un
        # correlativo y, si es negativo, vacia el cajon sin pasar por el
        # permiso de dueno que si exige la devolucion.
        raise _bad_request("el total de una venta tiene que ser positivo")

    paid = sum(item.amount_cents for item in payments)
    if paid != order.total_cents:
        raise _bad_request(
            f"los pagos suman {paid} céntimos y el total es {order.total_cents}"
        )

    # Cada pago tiene que ir en el mismo sentido que el ticket. Sin esto, un
    # pago de -76 EUR junto a otro de +100 EUR sumaba un total correcto de
    # 24 EUR y el cierre Z daba por salidos del cajon 76 EUR que nadie saco.
    quiere_negativo = order.total_cents < 0
    for item in payments:
        if item.amount_cents == 0 or (item.amount_cents < 0) != quiere_negativo:
            raise _bad_request("el importe de un pago no cuadra con el del ticket")

    for item in payments:
        if item.method not in ("cash", "card"):
            raise _bad_request(f"forma de pago no admitida: {item.method}")
        change = None
        if item.method == "cash" and item.tendered_cents is not None:
            if item.tendered_cents < item.amount_cents:
                raise _bad_request("lo entregado es menor que el importe a cobrar")
            change = item.tendered_cents - item.amount_cents
        order.payments.append(
            Payment(
                method=item.method,
                amount_cents=item.amount_cents,
                tendered_cents=item.tendered_cents,
                change_cents=change,
            )
        )

    issued_at = datetime.now(timezone.utc)
    ticket_series = series or get_settings().default_ticket_series
    number = next_ticket_number(db, ticket_series)

    order.ticket_series = ticket_series
    order.ticket_number = number
    order.ticket_full_number = format_ticket_number(ticket_series, number, issued_at)
    order.status = "paid"
    order.closed_at = issued_at
    order.opened_at = order.opened_at or issued_at
    if staff_id:
        order.staff_id = staff_id
    if device_id:
        order.device_id = device_id
    # La caja se resuelve en el servidor cuando no se indica: una venta sin
    # sesion queda fuera de todos los cierres Z para siempre.
    order.session_id = session_id or open_cash_session_id(db)

    db.flush()
    return order


def refund_order(
    db: Session,
    original: Order,
    *,
    line_ids: list[uuid.UUID] | None = None,
    staff_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> Order:
    """Crea una venta de signo contrario que apunta al ticket original.

    El ticket original no se modifica nunca. Sin `line_ids` devuelve el pedido
    completo; con ellos, solo esas líneas (devolución parcial).
    """
    if original.status not in ("paid", "partially_refunded"):
        raise _bad_request(
            f"no se puede devolver un ticket en estado {original.status}"
        )
    if original.refunds_order_id is not None:
        # Devolver una devolucion creaba una venta positiva sin que entrara
        # dinero en el cajon.
        raise _bad_request("una devolución no se devuelve")

    to_refund = original.lines
    if line_ids:
        wanted = set(line_ids)
        to_refund = [line for line in original.lines if line.id in wanted]
        if len(to_refund) != len(wanted):
            raise _bad_request("alguna línea no pertenece a este ticket")

    # Lo ya devuelto de este ticket. Sin esta comprobacion el mismo ticket se
    # podia devolver indefinidamente: tres llamadas devolvian el triple.
    ya_devueltas = set(
        db.scalars(
            select(OrderLine.refunds_line_id)
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                Order.refunds_order_id == original.id,
                OrderLine.refunds_line_id.is_not(None),
            )
        ).all()
    )
    pendientes = [line for line in to_refund if line.id not in ya_devueltas]
    if not pendientes:
        raise _bad_request("eso ya está devuelto")
    to_refund = pendientes

    refund = Order(
        channel=original.channel,
        status="open",
        refunds_order_id=original.id,
        customer_nif=original.customer_nif,
        customer_name=original.customer_name,
        note=reason,
        staff_id=staff_id,
        device_id=device_id,
        opened_at=datetime.now(timezone.utc),
    )
    for position, line in enumerate(to_refund):
        refund.lines.append(
            OrderLine(
                refunds_line_id=line.id,
                product_id=line.product_id,
                variant_id=line.variant_id,
                category_id=line.category_id,
                name_snapshot=line.name_snapshot,
                unit_price_cents=line.unit_price_cents,
                quantity=-line.quantity,
                vat_rate=line.vat_rate,
                line_total_cents=-line.line_total_cents,
                note=line.note,
                sort_order=position,
            )
        )

    apply_totals(refund)
    db.add(refund)

    # Devuelto del todo o solo en parte: lo decide si queda alguna linea sin
    # devolver, no el hecho de haber devuelto algo. Marcar como "refunded" un
    # ticket al que solo se le devolvio una linea perdia esa informacion.
    devueltas_ahora = ya_devueltas | {line.id for line in to_refund}
    quedan = [line for line in original.lines if line.id not in devueltas_ahora]
    original.status = "partially_refunded" if quedan else "refunded"

    db.flush()
    return refund
