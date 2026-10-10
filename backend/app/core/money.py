"""Importes en céntimos enteros. Nunca float.

En hostelería los precios de carta son con IVA incluido, así que la base se
calcula hacia atrás a partir del importe bruto, agrupando por tipo de IVA.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

VatRate = int  # porcentaje entero: 10, 21, 4, 0


def cents_from_str(value: str) -> int:
    """'12,50' o '12.50' -> 1250. Para importes teclados por el usuario."""
    normalized = value.strip().replace(" ", "").replace(",", ".")
    if not normalized:
        raise ValueError("importe vacío")
    return int(
        (Decimal(normalized) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def format_cents(cents: int) -> str:
    """1250 -> '12,50'. Formato español, sin símbolo de moneda."""
    sign = "-" if cents < 0 else ""
    units, hundredths = divmod(abs(cents), 100)
    return f"{sign}{units},{hundredths:02d}"


def base_from_gross(gross_cents: int, vat_rate: VatRate) -> int:
    """Base imponible de un importe con IVA incluido, redondeo al céntimo.

    base = gross / (1 + rate/100), redondeado a la mitad hacia arriba.
    """
    if vat_rate < 0:
        raise ValueError(f"tipo de IVA inválido: {vat_rate}")
    divisor = Decimal(100 + vat_rate) / Decimal(100)
    base = Decimal(gross_cents) / divisor
    return int(base.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class VatGroup:
    """Desglose de un tipo de IVA. Siempre base + vat == gross."""

    rate: VatRate
    gross_cents: int
    base_cents: int
    vat_cents: int


@dataclass(frozen=True)
class Totals:
    """Totales de un pedido. Siempre base_cents + vat_cents == total_cents."""

    total_cents: int
    base_cents: int
    vat_cents: int
    groups: tuple[VatGroup, ...]


def compute_totals(lines: list[tuple[int, VatRate]]) -> Totals:
    """Totales a partir de [(importe_bruto_de_linea, tipo_iva), ...].

    El IVA se calcula una sola vez por tipo sobre el bruto agregado, no línea a
    línea: así la suma de las bases cuadra exactamente con el total cobrado y no
    aparecen descuadres de un céntimo. La cuota se obtiene por diferencia
    (gross - base), lo que garantiza el cuadre por construcción.
    """
    gross_by_rate: dict[VatRate, int] = {}
    for gross_cents, rate in lines:
        gross_by_rate[rate] = gross_by_rate.get(rate, 0) + gross_cents

    groups = []
    for rate in sorted(gross_by_rate):
        gross = gross_by_rate[rate]
        base = base_from_gross(gross, rate)
        groups.append(
            VatGroup(rate=rate, gross_cents=gross, base_cents=base, vat_cents=gross - base)
        )

    return Totals(
        total_cents=sum(g.gross_cents for g in groups),
        base_cents=sum(g.base_cents for g in groups),
        vat_cents=sum(g.vat_cents for g in groups),
        groups=tuple(groups),
    )
