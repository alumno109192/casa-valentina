"""Caja: cierre Z, fianzas y descuadres."""

from __future__ import annotations


def _abrir(client, auth, fondo=10000):
    response = client.post(
        "/api/cash/session", json={"opening_float_cents": fondo}, headers=auth
    )
    assert response.status_code == 201, response.text
    return response.json()


def _vender(client, auth, catalog, session_id, method="cash", unidades=1):
    importe = 1200 * unidades
    body = {
        "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": unidades}],
        "payments": [{"method": method, "amount_cents": importe}],
        "session_id": session_id,
    }
    response = client.post("/api/sales", json=body, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_no_se_pueden_abrir_dos_cajas(client, auth):
    _abrir(client, auth)
    response = client.post(
        "/api/cash/session", json={"opening_float_cents": 0}, headers=auth
    )
    assert response.status_code == 409


def test_el_cierre_z_cuadra_con_la_suma_de_tickets(client, auth, catalog):
    """Criterio de aceptación: el Z cuadra con la suma de los tickets."""
    session = _abrir(client, auth, fondo=10000)
    _vender(client, auth, catalog, session["id"], "cash", 2)   # 24,00 efectivo
    _vender(client, auth, catalog, session["id"], "cash", 1)   # 12,00 efectivo
    _vender(client, auth, catalog, session["id"], "card", 1)   # 12,00 tarjeta

    z = client.get("/api/cash/session/z", headers=auth).json()

    assert z["ticket_count"] == 3
    assert z["sales_total_cents"] == 4800
    assert z["cash_sales_cents"] == 3600
    assert z["card_sales_cents"] == 1200
    assert z["expected_cash_cents"] == 10000 + 3600
    assert z["card_reconciled"] is False  # sin datáfono integrado


def test_el_desglose_de_iva_del_dia_cuadra(client, auth, catalog):
    session = _abrir(client, auth, fondo=0)
    _vender(client, auth, catalog, session["id"], "cash", 1)

    z = client.get("/api/cash/session/z", headers=auth).json()
    total_base = sum(g["base_cents"] for g in z["vat_breakdown"])
    total_cuota = sum(g["vat_cents"] for g in z["vat_breakdown"])
    assert total_base + total_cuota == z["sales_total_cents"]


def test_la_fianza_suma_a_caja_y_no_a_las_ventas(client, auth, catalog):
    """La fianza de paellera mueve caja pero no es una venta ni lleva IVA."""
    session = _abrir(client, auth, fondo=0)
    _vender(client, auth, catalog, session["id"], "cash", 1)

    fianza = client.post(
        "/api/cash/deposits",
        json={"customer_name": "Luis", "amount_cents": 2000},
        headers=auth,
    )
    assert fianza.status_code == 201, fianza.text

    z = client.get("/api/cash/session/z", headers=auth).json()
    assert z["sales_total_cents"] == 1200          # la fianza no es venta
    assert z["movements_cents"] == 2000
    assert z["expected_cash_cents"] == 1200 + 2000  # pero el dinero está en el cajón


def test_devolver_la_fianza_resta_de_caja(client, auth):
    session = _abrir(client, auth, fondo=0)
    fianza = client.post(
        "/api/cash/deposits",
        json={"customer_name": "Luis", "amount_cents": 2000},
        headers=auth,
    ).json()

    client.post(f"/api/cash/deposits/{fianza['id']}/return", headers=auth)

    z = client.get("/api/cash/session/z", headers=auth).json()
    assert z["movements_cents"] == 0
    assert z["expected_cash_cents"] == 0
    assert client.get("/api/cash/deposits", headers=auth).json() == []


def test_no_se_devuelve_dos_veces_la_misma_fianza(client, auth):
    _abrir(client, auth, fondo=0)
    fianza = client.post(
        "/api/cash/deposits", json={"amount_cents": 2000}, headers=auth
    ).json()
    client.post(f"/api/cash/deposits/{fianza['id']}/return", headers=auth)
    repetida = client.post(f"/api/cash/deposits/{fianza['id']}/return", headers=auth)
    assert repetida.status_code == 409


def test_descuadre_grande_exige_comentario(client, auth, catalog):
    session = _abrir(client, auth, fondo=0)
    _vender(client, auth, catalog, session["id"], "cash", 1)

    sin_comentario = client.post(
        "/api/cash/session/close", json={"counted_cash_cents": 0}, headers=auth
    )
    assert sin_comentario.status_code == 400

    con_comentario = client.post(
        "/api/cash/session/close",
        json={"counted_cash_cents": 0, "close_note": "robo de cambio"},
        headers=auth,
    )
    assert con_comentario.status_code == 200
    assert con_comentario.json()["difference_cents"] == -1200


def test_descuadre_pequeno_no_exige_comentario(client, auth, catalog):
    session = _abrir(client, auth, fondo=0)
    _vender(client, auth, catalog, session["id"], "cash", 1)

    cierre = client.post(
        "/api/cash/session/close", json={"counted_cash_cents": 1150}, headers=auth
    )
    assert cierre.status_code == 200
    assert cierre.json()["difference_cents"] == -50


def test_el_numero_z_avanza_en_cada_cierre(client, auth):
    primera = _abrir(client, auth, fondo=0)
    client.post(
        "/api/cash/session/close", json={"counted_cash_cents": 0}, headers=auth
    )
    segunda = _abrir(client, auth, fondo=0)
    assert segunda["z_number"] == primera["z_number"] + 1


def test_no_se_cierra_sin_caja_abierta(client, auth):
    response = client.post(
        "/api/cash/session/close", json={"counted_cash_cents": 0}, headers=auth
    )
    assert response.status_code == 409
