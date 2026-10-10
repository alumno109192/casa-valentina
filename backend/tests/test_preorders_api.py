"""Encargos: alta, recuento por franja y paso a venta."""

from __future__ import annotations

from datetime import date


def _encargo(client, auth, catalog, hora="13:15", unidades=2, nombre="María"):
    body = {
        "customer_name": nombre,
        "customer_phone": "600111222",
        "pickup_date": date.today().isoformat(),
        "pickup_time": hora,
        "channel": "phone",
        "lines": [
            {"variant_id": str(catalog["pollo"].id), "quantity": unidades}
        ],
    }
    response = client.post("/api/preorders", json=body, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_alta_de_encargo(client, auth, catalog):
    encargo = _encargo(client, auth, catalog)
    assert encargo["status"] == "pending"
    assert encargo["lines"][0]["name_snapshot"] == "Pollo asado"
    assert encargo["lines"][0]["quantity"] == 2


def test_recuento_de_pollos_por_franja(client, auth, catalog):
    """El resumen que permite planificar el asado."""
    _encargo(client, auth, catalog, hora="13:15", unidades=2)
    _encargo(client, auth, catalog, hora="13:25", unidades=4, nombre="Pedro")
    _encargo(client, auth, catalog, hora="13:45", unidades=3, nombre="Ana")

    board = client.get("/api/preorders/board", headers=auth).json()
    carga = {(item["slot"], item["product"]): item["quantity"] for item in board["load"]}

    assert carga[("13:00:00", "Pollo asado")] == 6   # 13:15 y 13:25 caen en la misma franja
    assert carga[("13:30:00", "Pollo asado")] == 3


def test_los_cancelados_no_cuentan_en_el_recuento(client, auth, catalog):
    encargo = _encargo(client, auth, catalog, hora="13:15", unidades=2)
    client.patch(
        f"/api/preorders/{encargo['id']}/status",
        json={"status": "cancelled"},
        headers=auth,
    )
    board = client.get("/api/preorders/board", headers=auth).json()
    assert board["load"] == []


def test_el_encargo_se_convierte_en_venta(client, auth, catalog):
    """Criterio de aceptación: un encargo pasa a venta y queda recogido."""
    encargo = _encargo(client, auth, catalog, unidades=2)

    venta = client.post(
        "/api/sales",
        json={
            "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": 2}],
            "payments": [{"method": "cash", "amount_cents": 2400}],
            "preorder_id": encargo["id"],
            "channel": "phone",
        },
        headers=auth,
    )
    assert venta.status_code == 201, venta.text
    assert venta.json()["channel"] == "phone"

    de_nuevo = client.get(f"/api/preorders/{encargo['id']}", headers=auth).json()
    assert de_nuevo["status"] == "collected"


def test_marcar_preparado(client, auth, catalog):
    encargo = _encargo(client, auth, catalog)
    response = client.patch(
        f"/api/preorders/{encargo['id']}/status",
        json={"status": "ready"},
        headers=auth,
    )
    assert response.json()["status"] == "ready"


def test_el_tablero_ordena_por_hora_de_recogida(client, auth, catalog):
    _encargo(client, auth, catalog, hora="14:00", nombre="Tarde")
    _encargo(client, auth, catalog, hora="13:00", nombre="Temprano")

    board = client.get("/api/preorders/board", headers=auth).json()
    assert [p["customer_name"] for p in board["preorders"]] == ["Temprano", "Tarde"]
