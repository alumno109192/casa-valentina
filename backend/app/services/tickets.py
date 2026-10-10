"""Asignación de número de ticket: correlativa por serie y sin huecos."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_year
from app.models.org import TicketCounter


def next_ticket_number(db: Session, series: str) -> int:
    """Reserva el siguiente número de la serie.

    La fila del contador se bloquea (`with_for_update`) mientras se incrementa,
    así dos cobros simultáneos no pueden recibir el mismo número. En SQLite el
    bloqueo lo da la propia transacción de escritura; en PostgreSQL, el SELECT
    FOR UPDATE. La restricción UNIQUE(ticket_series, ticket_number) es la red
    de seguridad final.
    """
    stmt = select(TicketCounter).where(TicketCounter.series == series)
    if db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()

    counter = db.scalars(stmt).one_or_none()
    if counter is None:
        counter = TicketCounter(series=series, last_number=0)
        db.add(counter)
        db.flush()

    counter.last_number += 1
    db.flush()
    return counter.last_number


def format_ticket_number(series: str, number: int, issued_at: datetime) -> str:
    """'T-2026-000123'.

    El número es continuo por serie y no se reinicia cada año: el año que
    se muestra es informativo. Reiniciarlo por ejercicio exigiría una fila
    de contador por serie y año, y está pendiente de decidir con la gestoría
    (ver docs/decisiones.md).

    El año se toma en hora local: con `issued_at.year` en UTC, un cobro a las
    00:30 del 1 de enero en Madrid salía numerado con el año anterior.
    """
    return f"{series}-{local_year(issued_at)}-{number:06d}"
