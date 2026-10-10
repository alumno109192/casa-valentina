"""Regresiones de la revisión de octubre de 2026.

Cada test fija un fallo concreto que estaba en el código y por el que se podía
sacar dinero del cajón, descuadrar un cierre Z o declarar un IVA que no
cuadraba con los tickets emitidos. Ninguno de estos casos lo detectaba la
suite anterior.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.core.money import compute_totals

CASH = "cash"
CARD = "card"


def _venta(catalog, **extra):
    cuerpo = {
        "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": 2}],
        "payments": [{"method": CASH, "amount_cents": 2400}],
    }
    cuerpo.update(extra)
    return cuerpo


def _token_de(client, pin: str) -> dict[str, str]:
    respuesta = client.post("/api/auth/login", json={"pin": pin})
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['token']}"}


# --- Dinero que salía del cajón sin permiso --------------------------------


def test_una_venta_de_cantidad_negativa_se_rechaza(client, auth, catalog, caja):
    """Era una devolución encubierta: el cajero no puede devolver (403) pero sí
    podía emitir una venta de -36 € que vaciaba el cajón igual, sin auditoría
    y sin apuntar al ticket original."""
    respuesta = client.post(
        "/api/sales",
        json={
            "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": -3}],
            "payments": [{"method": CASH, "amount_cents": -3600}],
        },
        headers=auth,
    )
    assert respuesta.status_code == 422, respuesta.text


def test_un_pago_negativo_colado_en_una_venta_se_rechaza(client, auth, catalog, caja):
    """-76 € de efectivo junto a +100 € de tarjeta sumaban el total correcto de
    24 €, y el cierre Z daba por salidos del cajón 76 € que nadie sacó."""
    respuesta = client.post(
        "/api/sales",
        json={
            "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": 2}],
            "payments": [
                {"method": CASH, "amount_cents": -7600},
                {"method": CARD, "amount_cents": 10000},
            ],
        },
        headers=auth,
    )
    assert respuesta.status_code == 422, respuesta.text


def test_una_venta_de_total_cero_no_gasta_numero_de_ticket(client, auth, catalog, caja):
    """La numeración correlativa sin huecos es el cimiento de VeriFactu: gastar
    correlativos en invitaciones de 0 € es un regalo envenenado."""
    respuesta = client.post(
        "/api/sales",
        json={
            "lines": [
                {
                    "quantity": 1,
                    "open_price_name": "Invitación",
                    "open_price_cents": 0,
                    "open_price_category_id": str(catalog["categoria_varios"].id),
                }
            ],
            "payments": [{"method": CASH, "amount_cents": 0}],
        },
        headers=auth,
    )
    assert respuesta.status_code == 422, respuesta.text


# --- Devoluciones ----------------------------------------------------------


def test_el_mismo_ticket_no_se_devuelve_dos_veces(client, auth, catalog, caja):
    """Tres llamadas devolvían el triple del importe cobrado."""
    venta = client.post("/api/sales", json=_venta(catalog), headers=auth).json()

    primera = client.post(f"/api/sales/{venta['id']}/refund", json={}, headers=auth)
    assert primera.status_code == 201, primera.text
    assert primera.json()["total_cents"] == -2400

    segunda = client.post(f"/api/sales/{venta['id']}/refund", json={}, headers=auth)
    assert segunda.status_code == 400, segunda.text


def test_la_misma_linea_no_se_devuelve_dos_veces(client, auth, catalog, caja):
    cuerpo = {
        "lines": [
            {"variant_id": str(catalog["pollo"].id), "quantity": 1},
            {"variant_id": str(catalog["alcachofas_racion"].id), "quantity": 1},
        ],
        "payments": [{"method": CASH, "amount_cents": 2000}],
    }
    venta = client.post("/api/sales", json=cuerpo, headers=auth).json()
    pollo = next(l for l in venta["lines"] if l["name_snapshot"] == "Pollo asado")

    primera = client.post(
        f"/api/sales/{venta['id']}/refund",
        json={"line_ids": [pollo["id"]]},
        headers=auth,
    )
    assert primera.status_code == 201, primera.text

    segunda = client.post(
        f"/api/sales/{venta['id']}/refund",
        json={"line_ids": [pollo["id"]]},
        headers=auth,
    )
    assert segunda.status_code == 400, segunda.text

    # Y la línea que sigue pendiente sí se puede devolver.
    alcachofas = next(
        l for l in venta["lines"] if l["name_snapshot"] == "Alcachofas"
    )
    tercera = client.post(
        f"/api/sales/{venta['id']}/refund",
        json={"line_ids": [alcachofas["id"]]},
        headers=auth,
    )
    assert tercera.status_code == 201, tercera.text

    original = client.get(f"/api/sales/{venta['id']}", headers=auth).json()
    assert original["status"] == "refunded"


def test_una_devolucion_no_se_devuelve(client, auth, catalog, caja):
    """Devolver una devolución creaba una venta positiva sin que entrara
    dinero en el cajón."""
    venta = client.post("/api/sales", json=_venta(catalog), headers=auth).json()
    devolucion = client.post(
        f"/api/sales/{venta['id']}/refund", json={}, headers=auth
    ).json()

    respuesta = client.post(
        f"/api/sales/{devolucion['id']}/refund", json={}, headers=auth
    )
    assert respuesta.status_code == 400, respuesta.text


def test_una_lista_de_lineas_vacia_no_devuelve_el_ticket_entero(
    client, auth, catalog, caja
):
    """`line_ids: []` es falsy y se interpretaba como «devuélvelo todo»."""
    venta = client.post("/api/sales", json=_venta(catalog), headers=auth).json()
    respuesta = client.post(
        f"/api/sales/{venta['id']}/refund", json={"line_ids": []}, headers=auth
    )
    assert respuesta.status_code == 422, respuesta.text


def test_la_devolucion_baja_el_efectivo_esperado_del_cierre(
    client, auth, catalog, caja
):
    """La devolución no entraba en ninguna sesión de caja: el cajón se quedaba
    a cero y el Z seguía esperando el importe de la venta."""
    client.post("/api/sales", json=_venta(catalog), headers=auth)

    antes = client.get("/api/cash/session/z", headers=auth).json()
    assert antes["expected_cash_cents"] == 10000 + 2400

    venta = client.get("/api/sales", headers=auth).json()[0]
    client.post(f"/api/sales/{venta['id']}/refund", json={}, headers=auth)

    despues = client.get("/api/cash/session/z", headers=auth).json()
    assert despues["expected_cash_cents"] == 10000
    assert despues["sales_total_cents"] == 0


def test_se_devuelve_por_donde_se_cobro(client, auth, catalog, caja):
    """Pagar siempre en efectivo vaciaba el cajón por una comida que había
    entrado por datáfono."""
    venta = client.post(
        "/api/sales",
        json=_venta(catalog, payments=[{"method": CARD, "amount_cents": 2400}]),
        headers=auth,
    ).json()

    devolucion = client.post(
        f"/api/sales/{venta['id']}/refund", json={}, headers=auth
    ).json()
    assert devolucion["payments"][0]["method"] == CARD

    # El efectivo esperado no se mueve: no ha salido dinero del cajón.
    informe = client.get("/api/cash/session/z", headers=auth).json()
    assert informe["expected_cash_cents"] == 10000


def test_devolver_exige_caja_abierta(client, auth, catalog, caja):
    venta = client.post("/api/sales", json=_venta(catalog), headers=auth).json()
    client.post(
        "/api/cash/session/close",
        json={"counted_cash_cents": 12400},
        headers=auth,
    )

    respuesta = client.post(f"/api/sales/{venta['id']}/refund", json={}, headers=auth)
    assert respuesta.status_code == 409, respuesta.text


# --- El cierre Z -----------------------------------------------------------


def test_una_venta_sin_session_id_entra_en_el_cierre_de_la_caja_abierta(
    client, auth, catalog, caja
):
    """El TPV no manda `session_id`, así que todas las ventas quedaban fuera
    de todos los cierres Z: el efectivo esperado era solo el fondo inicial."""
    respuesta = client.post("/api/sales", json=_venta(catalog), headers=auth)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["session_id"] == caja["id"]

    informe = client.get("/api/cash/session/z", headers=auth).json()
    assert informe["ticket_count"] == 1
    assert informe["cash_sales_cents"] == 2400
    assert informe["expected_cash_cents"] == 12400


def test_no_se_puede_imputar_una_venta_a_una_caja_que_no_es_la_abierta(
    client, auth, catalog, caja
):
    respuesta = client.post(
        "/api/sales",
        json=_venta(catalog, session_id=str(uuid.uuid4())),
        headers=auth,
    )
    assert respuesta.status_code == 409, respuesta.text


def test_el_iva_del_cierre_cuadra_con_el_de_los_tickets(client, auth, catalog, caja):
    """El Z reagrupaba todas las líneas del día y recalculaba la base sobre el
    bruto agregado. Diez bolsas de 0,15 € al 21 % dan 0,30 € de cuota en los
    tickets emitidos y 0,26 € reagrupando: los documentos son los que valen."""
    iva_de_los_tickets = 0
    for _ in range(10):
        venta = client.post(
            "/api/sales",
            json={
                "lines": [{"variant_id": str(catalog["bolsa"].id), "quantity": 1}],
                "payments": [{"method": CASH, "amount_cents": 15}],
            },
            headers=auth,
        ).json()
        iva_de_los_tickets += venta["vat_cents"]

    informe = client.get("/api/cash/session/z", headers=auth).json()
    iva_del_cierre = sum(g["vat_cents"] for g in informe["vat_breakdown"])
    base_del_cierre = sum(g["base_cents"] for g in informe["vat_breakdown"])

    assert iva_del_cierre == iva_de_los_tickets
    assert base_del_cierre + iva_del_cierre == informe["sales_total_cents"]
    # Y sigue sin coincidir con el cálculo agregado, que es el que estaba mal.
    assert compute_totals([(15, 21)] * 10).vat_cents != iva_de_los_tickets


def test_una_retirada_resta_del_efectivo_esperado(client, auth, catalog, caja):
    """Con el signo en manos del cliente, una retirada con importe positivo
    subía el efectivo esperado: el descuadre salía del doble del importe."""
    respuesta = client.post(
        "/api/cash/movements",
        json={"kind": "withdrawal", "amount_cents": 5000, "reason": "al banco"},
        headers=auth,
    )
    assert respuesta.status_code == 201, respuesta.text

    informe = client.get("/api/cash/session/z", headers=auth).json()
    assert informe["withdrawals_cents"] == -5000
    assert informe["expected_cash_cents"] == 5000


def test_una_retirada_sin_motivo_se_rechaza(client, auth, caja):
    respuesta = client.post(
        "/api/cash/movements",
        json={"kind": "withdrawal", "amount_cents": 5000},
        headers=auth,
    )
    assert respuesta.status_code == 422, respuesta.text


def test_el_cierre_desglosa_los_movimientos(client, auth, caja):
    """Una retirada de 200 y cuatro fianzas de 50 se anulaban en un único
    total y el arqueo no dejaba ver ninguna de las dos cosas."""
    client.post(
        "/api/cash/deposits", json={"amount_cents": 3000}, headers=auth
    )
    client.post(
        "/api/cash/movements",
        json={"kind": "withdrawal", "amount_cents": 3000, "reason": "al banco"},
        headers=auth,
    )

    informe = client.get("/api/cash/session/z", headers=auth).json()
    assert informe["movements_cents"] == 0  # se anulan entre sí
    assert informe["deposits_in_cents"] == 3000
    assert informe["withdrawals_cents"] == -3000
    assert informe["deposits_held_cents"] == 3000  # del cajón, pero no del negocio


def test_una_fianza_exige_caja_abierta(client, auth):
    """Sin caja abierta la fianza se grababa sin movimiento: el dinero quedaba
    en el cajón sin que ningún cierre lo esperara."""
    respuesta = client.post(
        "/api/cash/deposits", json={"amount_cents": 3000}, headers=auth
    )
    assert respuesta.status_code == 409, respuesta.text


def test_el_cajon_no_se_abre_sin_motivo(client, auth):
    """El motivo llegaba por la query, aceptaba la cadena vacía y acababa
    escrito en los logs de acceso del servidor."""
    assert client.post("/api/cash/drawer/open", json={}, headers=auth).status_code == 422
    assert (
        client.post(
            "/api/cash/drawer/open", json={"reason": "x"}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/cash/drawer/open",
            json={"reason": "cambio para el turno"},
            headers=auth,
        ).status_code
        == 201
    )


# --- IVA -------------------------------------------------------------------


@pytest.mark.parametrize("tipo", [99, 110, -5])
def test_un_tipo_de_iva_inventado_se_rechaza(client, auth, catalog, caja, tipo):
    """Un 99 % entraba en el desglose del cierre Z, y un -5 % hacía estallar
    el cobro con un 500."""
    respuesta = client.post(
        "/api/sales",
        json={
            "lines": [
                {
                    "quantity": 1,
                    "open_price_name": "Varios",
                    "open_price_cents": 10000,
                    "open_price_category_id": str(catalog["categoria_varios"].id),
                    "open_price_vat_rate": tipo,
                }
            ],
            "payments": [{"method": CASH, "amount_cents": 10000}],
        },
        headers=auth,
    )
    assert respuesta.status_code == 422, respuesta.text


def test_un_iva_del_cero_por_ciento_se_respeta(client, auth, catalog, caja):
    """`item.open_price_vat_rate or default` convertía el 0 % en 10 %: se
    declaraban 9,09 € de IVA de algo exento."""
    venta = client.post(
        "/api/sales",
        json={
            "lines": [
                {
                    "quantity": 1,
                    "open_price_name": "Exento",
                    "open_price_cents": 10000,
                    "open_price_category_id": str(catalog["categoria_varios"].id),
                    "open_price_vat_rate": 0,
                }
            ],
            "payments": [{"method": CASH, "amount_cents": 10000}],
        },
        headers=auth,
    ).json()

    assert venta["lines"][0]["vat_rate"] == 0
    assert venta["vat_cents"] == 0
    assert venta["base_cents"] == 10000


# --- Idempotencia ----------------------------------------------------------


def test_el_reenvio_identico_no_duplica_la_venta(client, auth, catalog, caja):
    identificador = str(uuid.uuid4())
    primera = client.post(
        "/api/sales", json=_venta(catalog, id=identificador), headers=auth
    ).json()
    segunda = client.post(
        "/api/sales", json=_venta(catalog, id=identificador), headers=auth
    ).json()

    assert primera["ticket_full_number"] == segunda["ticket_full_number"]
    assert client.get("/api/cash/session/z", headers=auth).json()["ticket_count"] == 1


def test_reusar_el_id_con_otro_contenido_no_se_cobra_en_silencio(
    client, auth, catalog, caja
):
    """Se devolvía el ticket viejo con un 201: una comida de 60 € se quedaba
    sin cobrar y el terminal creía que estaba cobrada."""
    identificador = str(uuid.uuid4())
    client.post("/api/sales", json=_venta(catalog, id=identificador), headers=auth)

    respuesta = client.post(
        "/api/sales",
        json={
            "id": identificador,
            "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": 5}],
            "payments": [{"method": CARD, "amount_cents": 6000}],
        },
        headers=auth,
    )
    assert respuesta.status_code == 409, respuesta.text


# --- Catálogo --------------------------------------------------------------


def test_una_variante_archivada_no_se_vende(client, auth, catalog, caja, db):
    media = catalog["alcachofas_media"]
    db.merge(media)
    media.archived = True
    db.commit()

    respuesta = client.post(
        "/api/sales",
        json={
            "lines": [{"variant_id": str(media.id), "quantity": 1}],
            "payments": [{"method": CASH, "amount_cents": 500}],
        },
        headers=auth,
    )
    assert respuesta.status_code == 400, respuesta.text

    # Y tampoco aparece en la botonera.
    familias = client.get("/api/catalog/pos").json()
    nombres = [
        v["name"]
        for familia in familias
        for p in familia["products"]
        if p["name"] == "Alcachofas"
        for v in p["variants"]
    ]
    assert nombres == ["Ración"]


def test_un_producto_agotado_no_se_vende_ni_sale_en_la_carta(
    client, auth, catalog, caja, db
):
    pollo = catalog["pollo"]
    producto = pollo.product
    db.merge(producto)
    producto.is_available = False
    db.commit()

    respuesta = client.post("/api/sales", json=_venta(catalog), headers=auth)
    assert respuesta.status_code == 400, respuesta.text

    carta = client.get("/api/catalog/menu").json()
    assert "Pollo asado" not in [
        p["name"] for familia in carta for p in familia["products"]
    ]
    # En el TPV sí sigue, para que el cajero sepa que existe.
    botonera = client.get("/api/catalog/pos").json()
    assert "Pollo asado" in [
        p["name"] for familia in botonera for p in familia["products"]
    ]


# --- Encargos --------------------------------------------------------------


def test_un_encargo_no_se_cobra_dos_veces(client, auth, catalog, caja):
    encargo = client.post(
        "/api/preorders",
        json={
            "customer_name": "Luis",
            "pickup_date": "2026-10-11",
            "pickup_time": "13:30",
            "lines": [{"variant_id": str(catalog["pollo"].id), "quantity": 1}],
        },
        headers=auth,
    ).json()

    primera = client.post(
        "/api/sales", json=_venta(catalog, preorder_id=encargo["id"]), headers=auth
    )
    assert primera.status_code == 201, primera.text

    segunda = client.post(
        "/api/sales", json=_venta(catalog, preorder_id=encargo["id"]), headers=auth
    )
    assert segunda.status_code == 409, segunda.text


# --- Autenticación ---------------------------------------------------------


def test_un_token_sin_caducidad_no_vale(client, owner):
    """PyJWT acepta un token sin `exp` si no se le exige: un token forjado era
    eterno."""
    ajustes = get_settings()
    forjado = jwt.encode(
        {"sub": str(owner.id)}, ajustes.jwt_secret, algorithm=ajustes.jwt_algorithm
    )
    respuesta = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {forjado}"}
    )
    assert respuesta.status_code == 401, respuesta.text


def test_un_token_con_sub_que_no_es_uuid_da_401_no_500(client):
    ajustes = get_settings()
    malo = jwt.encode(
        {
            "sub": "no-soy-un-uuid",
            "exp": datetime.now(timezone.utc).timestamp() + 600,
        },
        ajustes.jwt_secret,
        algorithm=ajustes.jwt_algorithm,
    )
    respuesta = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {malo}"}
    )
    assert respuesta.status_code == 401, respuesta.text


def test_la_plantilla_no_se_publica_sin_token(client, owner):
    """Regalaba el id y el rol del dueño a cualquiera en la red del local, que
    es la mitad del trabajo de quien quiera forjarse un token."""
    assert client.get("/api/auth/staff").status_code == 401
    assert client.get("/api/auth/staff", headers=_token_de(client, "1234")).status_code == 200


def test_el_freno_del_pin_no_se_esquiva_cambiando_de_device_id(client, owner):
    """La clave del contador era el `device_id` que manda el cliente: con uno
    nuevo en cada intento se recorrían los 10.000 PIN sin bloquearse."""
    ajustes = get_settings()
    codigos = []
    for intento in range(ajustes.max_pin_attempts + 3):
        respuesta = client.post(
            "/api/auth/login",
            json={"pin": "0000", "device_id": f"inventado-{intento}"},
        )
        codigos.append(respuesta.status_code)

    assert 429 in codigos, codigos
