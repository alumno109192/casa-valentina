import pytest

from app.core.money import (
    base_from_gross,
    cents_from_str,
    compute_totals,
    format_cents,
)


@pytest.mark.parametrize(
    "text,expected",
    [("12,50", 1250), ("12.50", 1250), ("3", 300), ("0,05", 5), ("1234,56", 123456)],
)
def test_cents_from_str(text, expected):
    assert cents_from_str(text) == expected


def test_cents_from_str_redondea_tercer_decimal():
    assert cents_from_str("1,005") == 101  # half-up, no bankers rounding


def test_cents_from_str_rechaza_vacio():
    with pytest.raises(ValueError):
        cents_from_str("  ")


@pytest.mark.parametrize(
    "cents,expected", [(1250, "12,50"), (300, "3,00"), (5, "0,05"), (-850, "-8,50")]
)
def test_format_cents(cents, expected):
    assert format_cents(cents) == expected


def test_base_from_gross_pollo_asado():
    # 12,00 € con IVA 10% -> base 10,91, cuota 1,09
    assert base_from_gross(1200, 10) == 1091


def test_base_from_gross_bolsa_21():
    # 0,15 € con IVA 21% -> base 0,12
    assert base_from_gross(15, 21) == 12


def test_base_from_gross_sin_iva():
    assert base_from_gross(500, 0) == 500


def test_totales_cuadran_un_solo_tipo():
    # 2 pollos a 12,00 + patatas 4,50 + Coca-Cola 3,00, todo al 10%
    t = compute_totals([(2400, 10), (450, 10), (300, 10)])
    assert t.total_cents == 3150
    assert t.base_cents + t.vat_cents == t.total_cents
    assert t.base_cents == 2864
    assert t.vat_cents == 286


def test_totales_cuadran_tipos_mixtos():
    t = compute_totals([(1200, 10), (15, 21)])
    assert t.total_cents == 1215
    assert t.base_cents + t.vat_cents == t.total_cents
    rates = {g.rate: g for g in t.groups}
    assert rates[10].base_cents == 1091 and rates[10].vat_cents == 109
    assert rates[21].base_cents == 12 and rates[21].vat_cents == 3


def test_el_iva_se_agrupa_por_tipo_no_por_linea():
    """Tres cafés de 1,20: agregado da 327 de base; línea a línea daría 3x109=327
    aquí, pero con importes como 0,95 la diferencia aparece. Caso de control."""
    agregado = compute_totals([(95, 10)] * 3)
    por_linea = base_from_gross(95, 10) * 3
    assert agregado.total_cents == 285
    assert agregado.base_cents == 259  # 285/1.1 = 259,09 -> 259
    assert por_linea == 258  # suma de 86 tres veces: descuadraría un céntimo
    assert agregado.base_cents + agregado.vat_cents == agregado.total_cents


def test_pedido_vacio():
    t = compute_totals([])
    assert (t.total_cents, t.base_cents, t.vat_cents, t.groups) == (0, 0, 0, ())


def test_devolucion_importes_negativos():
    t = compute_totals([(-1200, 10)])
    assert t.total_cents == -1200
    assert t.base_cents + t.vat_cents == -1200
