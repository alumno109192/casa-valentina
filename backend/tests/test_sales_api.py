"""Flujo de cobro, numeración, devoluciones e idempotencia."""

from __future__ import annotations

import uuid

CASH = "cash"
CARD = "card"


def _sale(catalog, **extra):
    body = {
        "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": 2}],
        "payments": [{"method": CASH, "amount_cents": 2400, "tendered_cents": 5000}],
    }
    body.update(extra)
    return body


def test_venta_simple_calcula_iva_y_cambio(client, auth, catalog):
    response = client.post("/api/sales", json=_sale(catalog), headers=auth)
    assert response.status_code == 201, response.text
    order = response.json()

    assert order["total_cents"] == 2400
    assert order["base_cents"] + order["vat_cents"] == 2400
    assert order["base_cents"] == 2182  # 24,00 / 1,10
    assert order["payments"][0]["change_cents"] == 2600
    assert order["status"] == "paid"


def test_numero_de_ticket_correlativo_sin_huecos(client, auth, catalog):
    numeros = []
    for _ in range(5):
        response = client.post("/api/sales", json=_sale(catalog), headers=auth)
        assert response.status_code == 201
        numeros.append(response.json()["ticket_full_number"])

    sufijos = [int(n.split("-")[-1]) for n in numeros]
    assert sufijos == [1, 2, 3, 4, 5]
    assert all(n.startswith("T-") for n in numeros)


def test_media_racion_se_cobra_a_su_precio(client, auth, catalog):
    body = {
        "lines": [{"variant_id": str(catalog["alcachofas_media"].id), "quantity": 1}],
        "payments": [{"method": CASH, "amount_cents": 500}],
    }
    order = client.post("/api/sales", json=body, headers=auth).json()
    assert order["total_cents"] == 500
    assert order["lines"][0]["name_snapshot"] == "Alcachofas (Media)"


def test_racion_entera_no_lleva_sufijo(client, auth, catalog):
    body = {
        "lines": [{"variant_id": str(catalog["alcachofas_racion"].id), "quantity": 1}],
        "payments": [{"method": CASH, "amount_cents": 800}],
    }
    order = client.post("/api/sales", json=body, headers=auth).json()
    assert order["lines"][0]["name_snapshot"] == "Alcachofas"


def test_pago_mixto(client, auth, catalog):
    body = {
        "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": 2}],
        "payments": [
            {"method": CASH, "amount_cents": 1000},
            {"method": CARD, "amount_cents": 1400},
        ],
    }
    response = client.post("/api/sales", json=body, headers=auth)
    assert response.status_code == 201
    assert len(response.json()["payments"]) == 2


def test_rechaza_pago_que_no_cuadra(client, auth, catalog):
    body = _sale(catalog, payments=[{"method": CASH, "amount_cents": 2000}])
    response = client.post("/api/sales", json=body, headers=auth)
    assert response.status_code == 400
    assert "total" in response.json()["detail"]


def test_rechaza_entregado_menor_que_el_importe(client, auth, catalog):
    body = _sale(
        catalog,
        payments=[{"method": CASH, "amount_cents": 2400, "tendered_cents": 2000}],
    )
    assert client.post("/api/sales", json=body, headers=auth).status_code == 400


def test_desglose_de_iva_por_tipos(client, auth, catalog):
    body = {
        "lines": [
            {"variant_id": str(catalog["pollo"].id), "quantity": 1},
            {"variant_id": str(catalog["bolsa"].id), "quantity": 1},
        ],
        "payments": [{"method": CASH, "amount_cents": 1215}],
    }
    order = client.post("/api/sales", json=body, headers=auth).json()

    assert order["total_cents"] == 1215
    assert order["base_cents"] + order["vat_cents"] == 1215
    por_tipo = {g["rate"]: g for g in order["vat_breakdown"]}
    assert por_tipo[10]["base_cents"] == 1091
    assert por_tipo[21]["base_cents"] == 12


def test_precio_libre_necesita_familia(client, auth, catalog):
    body = {
        "lines": [
            {"open_price_name": "Encargo especial", "open_price_cents": 2500}
        ],
        "payments": [{"method": CASH, "amount_cents": 2500}],
    }
    response = client.post("/api/sales", json=body, headers=auth)
    assert response.status_code == 400
    assert "familia" in response.json()["detail"]


def test_precio_libre_con_familia(client, auth, catalog):
    body = {
        "lines": [
            {
                "open_price_name": "Encargo especial",
                "open_price_cents": 2500,
                "open_price_category_id": str(catalog["categoria_varios"].id),
            }
        ],
        "payments": [{"method": CASH, "amount_cents": 2500}],
    }
    order = client.post("/api/sales", json=body, headers=auth).json()
    assert order["total_cents"] == 2500
    assert order["lines"][0]["name_snapshot"] == "Encargo especial"


def test_producto_de_precio_libre_exige_importe(client, auth, catalog):
    body = {
        "lines": [{"variant_id": str(catalog["libre"].id), "quantity": 1}],
        "payments": [{"method": CASH, "amount_cents": 100}],
    }
    response = client.post("/api/sales", json=body, headers=auth)
    assert response.status_code == 400
    assert "importe" in response.json()["detail"]


def test_reenviar_la_misma_venta_no_la_duplica(client, auth, catalog):
    """Criterio de aceptación: al recuperar la red no se duplican ventas."""
    sale_id = str(uuid.uuid4())
    body = _sale(catalog, id=sale_id)

    primera = client.post("/api/sales", json=body, headers=auth).json()
    segunda = client.post("/api/sales", json=body, headers=auth).json()

    assert primera["ticket_full_number"] == segunda["ticket_full_number"]
    assert len(client.get("/api/sales", headers=auth).json()) == 1


def test_el_precio_del_ticket_no_cambia_si_cambia_la_tarifa(
    client, auth, catalog, db
):
    order = client.post("/api/sales", json=_sale(catalog), headers=auth).json()

    variante = catalog["pollo"]
    db.merge(variante)
    variante.price_cents = 1500
    db.commit()

    de_nuevo = client.get(f"/api/sales/{order['id']}", headers=auth).json()
    assert de_nuevo["lines"][0]["unit_price_cents"] == 1200


def test_devolucion_total(client, auth, catalog, caja):
    venta = client.post("/api/sales", json=_sale(catalog), headers=auth).json()

    response = client.post(
        f"/api/sales/{venta['id']}/refund", json={"reason": "cliente"}, headers=auth
    )
    assert response.status_code == 201, response.text
    devolucion = response.json()

    assert devolucion["total_cents"] == -2400
    assert devolucion["refunds_order_id"] == venta["id"]
    assert devolucion["ticket_full_number"] != venta["ticket_full_number"]

    original = client.get(f"/api/sales/{venta['id']}", headers=auth).json()
    assert original["status"] == "refunded"
    assert original["total_cents"] == 2400  # el ticket original no se toca


def test_devolucion_parcial(client, auth, catalog, caja):
    body = {
        "lines": [
            {"variant_id": str(catalog["pollo"].id), "quantity": 1},
            {"variant_id": str(catalog["alcachofas_racion"].id), "quantity": 1},
        ],
        "payments": [{"method": CASH, "amount_cents": 2000}],
    }
    venta = client.post("/api/sales", json=body, headers=auth).json()
    linea_pollo = next(
        l for l in venta["lines"] if l["name_snapshot"] == "Pollo asado"
    )

    devolucion = client.post(
        f"/api/sales/{venta['id']}/refund",
        json={"line_ids": [linea_pollo["id"]]},
        headers=auth,
    ).json()

    assert devolucion["total_cents"] == -1200
    assert len(devolucion["lines"]) == 1

    # El original queda parcialmente devuelto, no devuelto del todo: le quedan
    # 8,00 EUR que el cliente si pago.
    original = client.get(f"/api/sales/{venta['id']}", headers=auth).json()
    assert original["status"] == "partially_refunded"


def test_el_cajero_no_puede_devolver(client, auth, catalog, caja, cashier):
    token = client.post("/api/auth/login", json={"pin": "5678"}).json()["token"]
    cajero = {"Authorization": f"Bearer {token}"}

    venta = client.post("/api/sales", json=_sale(catalog), headers=cajero).json()
    response = client.post(f"/api/sales/{venta['id']}/refund", json={}, headers=cajero)
    assert response.status_code == 403


def test_sin_token_no_se_cobra(client, catalog):
    assert client.post("/api/sales", json=_sale(catalog)).status_code == 401
