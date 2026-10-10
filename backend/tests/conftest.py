"""Fixtures: una base SQLite temporal por test y un cliente autenticado."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.security import hash_pin
from app.main import app
from app.models import Base, Category, Product, ProductVariant, Staff


@pytest.fixture(autouse=True)
def _freno_limpio() -> Iterator[None]:
    """El contador de intentos de PIN vive en memoria del módulo y persiste
    entre tests: sin limpiarlo, los intentos fallidos de un test bloquean la
    IP y dejan sin entrar a los siguientes."""
    from app.api.auth import _attempts

    _attempts.clear()
    yield
    _attempts.clear()


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",  # en memoria
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def owner(db: Session) -> Staff:
    staff = Staff(name="Dueño", pin_hash=hash_pin("1234"), role="owner")
    db.add(staff)
    db.commit()
    return staff


@pytest.fixture
def cashier(db: Session) -> Staff:
    staff = Staff(name="Ana", pin_hash=hash_pin("5678"), role="cashier")
    db.add(staff)
    db.commit()
    return staff


@pytest.fixture
def auth(client: TestClient, owner: Staff) -> dict[str, str]:
    """Cabecera con el token del dueño."""
    response = client.post("/api/auth/login", json={"pin": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def caja(client: TestClient, auth: dict[str, str]) -> dict:
    """Caja abierta con fondo de 100,00 EUR.

    Cobrar y devolver exigen caja abierta: el dinero que entra o sale del
    cajon tiene que caer en algun cierre Z.
    """
    response = client.post(
        "/api/cash/session", json={"opening_float_cents": 10000}, headers=auth
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def catalog(db: Session) -> dict[str, ProductVariant]:
    """Catálogo mínimo: pollo (sin media), alcachofas (ración y media) y bolsa al 21 %."""
    comida = Category(name="Pollo", sort_order=0)
    varios = Category(name="Varios", sort_order=1)
    db.add_all([comida, varios])
    db.flush()

    pollo = Product(
        category_id=comida.id, name="Pollo asado", short_name="POLLO", vat_rate=10
    )
    pollo.variants.append(
        ProductVariant(name="Ración", price_cents=1200, is_default=True)
    )

    alcachofas = Product(
        category_id=comida.id, name="Alcachofas", short_name="Alcachofas", vat_rate=10
    )
    alcachofas.variants.append(
        ProductVariant(name="Ración", price_cents=800, is_default=True, sort_order=0)
    )
    alcachofas.variants.append(
        ProductVariant(name="Media", price_cents=500, sort_order=1)
    )

    bolsa = Product(
        category_id=varios.id, name="Bolsa", short_name="Bolsa", vat_rate=21
    )
    bolsa.variants.append(
        ProductVariant(name="Unidad", price_cents=15, is_default=True)
    )

    libre = Product(
        category_id=varios.id,
        name="Precio libre",
        short_name="LIBRE",
        vat_rate=10,
        is_open_price=True,
    )
    libre.variants.append(
        ProductVariant(name="Importe", price_cents=0, is_default=True)
    )

    db.add_all([pollo, alcachofas, bolsa, libre])
    db.commit()

    return {
        "pollo": pollo.variants[0],
        "alcachofas_racion": alcachofas.variants[0],
        "alcachofas_media": alcachofas.variants[1],
        "bolsa": bolsa.variants[0],
        "libre": libre.variants[0],
        "categoria_varios": varios,
    }
