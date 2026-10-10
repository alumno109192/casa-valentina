"""Caja: sesión, movimientos, fianzas y cierre Z."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentStaff, DbSession, Owner
from app.core.money import compute_totals
from app.models.audit import AuditLog
from app.models.cash import CashMovement, CashSession, Deposit
from app.models.sales import Order, Payment
from app.schemas.sales import (
    MovementIn,
    SessionCloseIn,
    SessionOpenIn,
    SessionOut,
    VatGroupOut,
    ZReport,
)

router = APIRouter(prefix="/cash", tags=["caja"])


def _open_session(db: DbSession) -> CashSession | None:
    return db.scalars(
        select(CashSession).where(CashSession.closed_at.is_(None))
    ).first()


@router.get("/session", response_model=SessionOut | None)
def current_session(db: DbSession, _: CurrentStaff) -> SessionOut | None:
    session = _open_session(db)
    return SessionOut.model_validate(session) if session else None


@router.post("/session", response_model=SessionOut, status_code=201)
def open_session(
    data: SessionOpenIn, db: DbSession, staff: CurrentStaff
) -> SessionOut:
    if _open_session(db) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya hay una caja abierta")

    last_z = db.scalar(select(func.max(CashSession.z_number))) or 0
    session = CashSession(
        device_id=data.device_id,
        z_number=last_z + 1,
        opened_by=staff.id,
        opened_at=datetime.now(timezone.utc),
        opening_float_cents=data.opening_float_cents,
    )
    db.add(session)
    db.flush()
    return SessionOut.model_validate(session)


@router.post("/movements", status_code=201)
def add_movement(
    data: MovementIn, db: DbSession, staff: CurrentStaff
) -> dict[str, str]:
    """Retiradas, aportaciones al cambio y entrada o salida de fianzas."""
    session = _open_session(db)
    if session is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "no hay caja abierta")

    movement = CashMovement(
        session_id=session.id,
        kind=data.kind,
        amount_cents=data.amount_cents,
        reason=data.reason,
        related_deposit_id=data.related_deposit_id,
        staff_id=staff.id,
    )
    db.add(movement)
    db.add(
        AuditLog(
            staff_id=staff.id,
            action="cash_movement",
            entity="cash_movement",
            payload={"kind": data.kind, "amount_cents": data.amount_cents},
        )
    )
    db.flush()
    return {"id": str(movement.id)}


def build_z_report(db: DbSession, session: CashSession) -> ZReport:
    """Calcula el cierre: ventas, movimientos y efectivo esperado.

    efectivo esperado = fondo inicial + ventas en efectivo + movimientos
    (las fianzas recibidas suman y las devueltas restan, porque el dinero está
    físicamente en el cajón aunque no sea una venta).
    """
    orders = db.scalars(
        select(Order).where(
            Order.session_id == session.id, Order.status.in_(("paid", "refunded"))
        )
    ).all()
    order_ids = [o.id for o in orders]

    cash_sales = card_sales = 0
    if order_ids:
        rows = db.execute(
            select(Payment.method, func.sum(Payment.amount_cents))
            .where(Payment.order_id.in_(order_ids))
            .group_by(Payment.method)
        ).all()
        totals_by_method = {method: int(amount or 0) for method, amount in rows}
        cash_sales = totals_by_method.get("cash", 0)
        card_sales = totals_by_method.get("card", 0)

    movements = int(
        db.scalar(
            select(func.coalesce(func.sum(CashMovement.amount_cents), 0)).where(
                CashMovement.session_id == session.id
            )
        )
        or 0
    )

    expected = session.opening_float_cents + cash_sales + movements

    # Desglose de IVA de la jornada, reagrupando todas las líneas
    vat_lines: list[tuple[int, int]] = []
    for order in orders:
        for line in order.lines:
            vat_lines.append((line.line_total_cents, line.vat_rate))
    totals = compute_totals(vat_lines)

    return ZReport(
        session=SessionOut.model_validate(session),
        ticket_count=len(orders),
        sales_total_cents=sum(o.total_cents for o in orders),
        cash_sales_cents=cash_sales,
        card_sales_cents=card_sales,
        movements_cents=movements,
        expected_cash_cents=expected,
        counted_cash_cents=session.counted_cash_cents,
        difference_cents=session.difference_cents,
        vat_breakdown=[
            VatGroupOut(
                rate=g.rate,
                gross_cents=g.gross_cents,
                base_cents=g.base_cents,
                vat_cents=g.vat_cents,
            )
            for g in totals.groups
        ],
        card_reconciled=False,
    )


@router.get("/session/z", response_model=ZReport)
def preview_z(db: DbSession, _: CurrentStaff) -> ZReport:
    """Cifras del cierre antes de contar, para que el cajero compare."""
    session = _open_session(db)
    if session is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "no hay caja abierta")
    return build_z_report(db, session)


@router.post("/session/close", response_model=ZReport)
def close_session(
    data: SessionCloseIn, db: DbSession, staff: CurrentStaff
) -> ZReport:
    session = _open_session(db)
    if session is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "no hay caja abierta")

    report = build_z_report(db, session)
    difference = data.counted_cash_cents - report.expected_cash_cents

    # Un descuadre de más de 5 € tiene que ir explicado
    if abs(difference) > 500 and not data.close_note:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"el descuadre es de {difference} céntimos: hace falta un comentario",
        )

    session.closed_by = staff.id
    session.closed_at = datetime.now(timezone.utc)
    session.counted_cash_cents = data.counted_cash_cents
    session.expected_cash_cents = report.expected_cash_cents
    session.card_total_cents = report.card_sales_cents
    session.difference_cents = difference
    session.close_note = data.close_note
    db.flush()

    db.add(
        AuditLog(
            staff_id=staff.id,
            action="close_session",
            entity="cash_session",
            entity_id=session.id,
            payload={"difference_cents": difference, "z_number": session.z_number},
        )
    )
    return build_z_report(db, session)


@router.post("/drawer/open", status_code=201)
def open_drawer(db: DbSession, staff: Owner, reason: str) -> dict[str, bool]:
    """Apertura del cajón sin venta. Exige motivo y queda registrada."""
    db.add(
        AuditLog(
            staff_id=staff.id, action="open_drawer", payload={"reason": reason}
        )
    )
    return {"ok": True}


# --- Fianzas de paellera ----------------------------------------------------

class DepositIn(BaseModel):
    item: str = "Paellera"
    customer_name: str | None = None
    customer_phone: str | None = None
    amount_cents: int = Field(gt=0)


class DepositOut(BaseModel):
    id: uuid.UUID
    item: str
    customer_name: str | None = None
    customer_phone: str | None = None
    amount_cents: int
    status: str

    model_config = {"from_attributes": True}


@router.get("/deposits", response_model=list[DepositOut])
def list_deposits(db: DbSession, _: CurrentStaff) -> list[DepositOut]:
    rows = db.scalars(
        select(Deposit).where(Deposit.status == "held").order_by(Deposit.taken_at)
    ).all()
    return [DepositOut.model_validate(d) for d in rows]


@router.post("/deposits", response_model=DepositOut, status_code=201)
def take_deposit(
    data: DepositIn, db: DbSession, staff: CurrentStaff
) -> DepositOut:
    """La fianza no es una venta y no lleva IVA: solo mueve caja."""
    session = _open_session(db)
    deposit = Deposit(**data.model_dump(), taken_at=datetime.now(timezone.utc))
    db.add(deposit)
    db.flush()

    if session is not None:
        db.add(
            CashMovement(
                session_id=session.id,
                kind="deposit_in",
                amount_cents=deposit.amount_cents,
                reason=f"Fianza {deposit.item} · {deposit.customer_name or 's/n'}",
                related_deposit_id=deposit.id,
                staff_id=staff.id,
            )
        )
    db.flush()
    return DepositOut.model_validate(deposit)


@router.post("/deposits/{deposit_id}/return", response_model=DepositOut)
def return_deposit(
    deposit_id: uuid.UUID, db: DbSession, staff: CurrentStaff
) -> DepositOut:
    deposit = db.get(Deposit, deposit_id)
    if deposit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "fianza no encontrada")
    if deposit.status != "held":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"la fianza ya está {deposit.status}"
        )

    deposit.status = "returned"
    deposit.returned_at = datetime.now(timezone.utc)

    session = _open_session(db)
    if session is not None:
        db.add(
            CashMovement(
                session_id=session.id,
                kind="deposit_out",
                amount_cents=-deposit.amount_cents,
                reason=f"Devolución fianza {deposit.item}",
                related_deposit_id=deposit.id,
                staff_id=staff.id,
            )
        )
    db.flush()
    return DepositOut.model_validate(deposit)
