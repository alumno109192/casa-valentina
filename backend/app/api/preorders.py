"""Encargos: alta rápida, pantalla del día y recuento de pollos."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, time

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentStaff, DbSession
from app.models.catalog import ProductVariant
from app.models.preorders import Preorder, PreorderLine
from app.schemas.sales import PreorderIn, PreorderOut, PreorderStatusIn

router = APIRouter(prefix="/preorders", tags=["encargos"])


class SlotLoad(BaseModel):
    """Unidades comprometidas de un producto en una franja de media hora."""

    slot: time
    product: str
    quantity: int


class DayBoard(BaseModel):
    """Lo que ve el mostrador: encargos del día y carga por franja."""

    day: date
    preorders: list[PreorderOut]
    load: list[SlotLoad]


def _loaded(db: DbSession, preorder_id: uuid.UUID) -> Preorder | None:
    return db.scalars(
        select(Preorder)
        .options(selectinload(Preorder.lines))
        .where(Preorder.id == preorder_id)
    ).one_or_none()


@router.post("", response_model=PreorderOut, status_code=201)
def create_preorder(
    data: PreorderIn, db: DbSession, staff: CurrentStaff
) -> PreorderOut:
    preorder = Preorder(
        **data.model_dump(exclude={"lines"}), created_by=staff.id
    )

    for line in data.lines:
        name = line.name_snapshot
        if line.variant_id is not None:
            variant = db.scalars(
                select(ProductVariant)
                .options(selectinload(ProductVariant.product))
                .where(ProductVariant.id == line.variant_id)
            ).one_or_none()
            if variant is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "la variante no existe"
                )
            name = (
                variant.product.name
                if variant.is_default
                else f"{variant.product.name} ({variant.name})"
            )
        if not name:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "la línea necesita producto o texto"
            )
        preorder.lines.append(
            PreorderLine(
                variant_id=line.variant_id,
                name_snapshot=name,
                quantity=line.quantity,
                note=line.note,
            )
        )

    db.add(preorder)
    db.flush()
    return PreorderOut.model_validate(preorder)


def _slot(moment: time) -> time:
    """Agrupa en franjas de media hora: 13:17 -> 13:00, 13:42 -> 13:30."""
    return time(hour=moment.hour, minute=0 if moment.minute < 30 else 30)


@router.get("/board", response_model=DayBoard)
def day_board(db: DbSession, _: CurrentStaff, day: date | None = None) -> DayBoard:
    """Encargos del día más el recuento por franja.

    El recuento es lo que permite planificar el asado: cuántos pollos hay
    comprometidos entre las 13:00 y las 13:30, por ejemplo.
    """
    target = day or date.today()
    rows = db.scalars(
        select(Preorder)
        .options(selectinload(Preorder.lines))
        .where(Preorder.pickup_date == target)
        .order_by(Preorder.pickup_time)
    ).all()

    counts: dict[tuple[time, str], int] = defaultdict(int)
    for preorder in rows:
        if preorder.status in ("cancelled", "no_show"):
            continue
        slot = _slot(preorder.pickup_time)
        for line in preorder.lines:
            counts[(slot, line.name_snapshot)] += line.quantity

    load = [
        SlotLoad(slot=slot, product=product, quantity=quantity)
        for (slot, product), quantity in sorted(counts.items())
    ]
    return DayBoard(
        day=target,
        preorders=[PreorderOut.model_validate(p) for p in rows],
        load=load,
    )


@router.get("/{preorder_id}", response_model=PreorderOut)
def get_preorder(
    preorder_id: uuid.UUID, db: DbSession, _: CurrentStaff
) -> PreorderOut:
    preorder = _loaded(db, preorder_id)
    if preorder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "encargo no encontrado")
    return PreorderOut.model_validate(preorder)


@router.patch("/{preorder_id}/status", response_model=PreorderOut)
def set_status(
    preorder_id: uuid.UUID,
    data: PreorderStatusIn,
    db: DbSession,
    _: CurrentStaff,
) -> PreorderOut:
    """Preparado, recogido, no presentado o cancelado.

    'collected' lo pone normalmente la venta al cobrar el encargo; aquí se
    permite para corregir a mano.
    """
    preorder = _loaded(db, preorder_id)
    if preorder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "encargo no encontrado")
    preorder.status = data.status
    db.flush()
    return PreorderOut.model_validate(preorder)
