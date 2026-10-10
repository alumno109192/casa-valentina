"""Motor y sesiones de SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    future=True,
    # timeout: dos cobros simultáneos esperan su turno en lugar de fallar
    connect_args=(
        {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
    ),
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        """SQLite no respeta las claves ajenas por defecto; en PostgreSQL esto
        no hace falta. WAL evita bloqueos entre lectura y escritura."""
        # Fuera el BEGIN implícito de pysqlite: lo emitimos nosotros abajo.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection):
        """Toma el bloqueo de escritura al abrir la transacción.

        Con el BEGIN diferido de serie, dos cobros a la vez leen el contador de
        tickets y el segundo muere con «database is locked» al escribir: el
        cajero se come un 500 en hora punta. Con BEGIN IMMEDIATE espera su
        turno. En PostgreSQL esto no se usa: allí el bloqueo real lo da el
        SELECT ... FOR UPDATE de services/tickets.py.
        """
        connection.exec_driver_sql("BEGIN IMMEDIATE")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
