"""Integridad de caja y devoluciones

Añade lo que hacía falta para que la base de datos, y no solo el código,
impida los descuadres:

* `order_lines.refunds_line_id`: qué línea devuelve cada línea de devolución.
  Es lo que permite rechazar la segunda devolución de la misma línea.
* índices de las consultas que de verdad se hacen (el cierre Z filtraba por
  `session_id`, que no tenía índice).
* unicidad del número Z, del plato del día y del número de ticket impreso.
* una sola caja abierta a la vez, garantizada por la base y no por un
  `SELECT` seguido de un `INSERT`.
* CHECK en las columnas de estado: un estado desconocido se cae fuera de los
  filtros de los informes, y entonces hay dinero cobrado que no aparece en
  ningún cierre.

Revision ID: b1c7a4e92f30
Revises: 43e64d137f97
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c7a4e92f30"
down_revision = "43e64d137f97"
branch_labels = None
depends_on = None


# (tabla, nombre, columna, valores admitidos)
CHECKS = [
    (
        "orders",
        "ck_orders_status",
        "status",
        ("open", "paid", "partially_refunded", "refunded", "voided"),
    ),
    (
        "orders",
        "ck_orders_channel",
        "channel",
        ("counter", "phone", "whatsapp", "menu_online"),
    ),
    ("payments", "ck_payments_method", "method", ("cash", "card")),
    ("deposits", "ck_deposits_status", "status", ("held", "returned", "kept")),
    (
        "preorders",
        "ck_preorders_status",
        "status",
        ("pending", "ready", "collected", "cancelled", "no_show"),
    ),
    (
        "cash_movements",
        "ck_cash_movements_kind",
        "kind",
        ("deposit_in", "deposit_out", "withdrawal", "float_in", "correction"),
    ),
    ("staff", "ck_staff_role", "role", ("owner", "cashier")),
]


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    lista = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({lista})"


def upgrade() -> None:
    # --- Enlace de la línea devuelta ---------------------------------------
    with op.batch_alter_table("order_lines") as batch:
        batch.add_column(sa.Column("refunds_line_id", sa.CHAR(36), nullable=True))
        batch.create_foreign_key(
            "fk_order_lines_refunds_line_id",
            "order_lines",
            ["refunds_line_id"],
            ["id"],
        )
    op.create_index(
        "ix_order_lines_refunds_line_id", "order_lines", ["refunds_line_id"]
    )

    # --- Índices de las consultas reales -----------------------------------
    # El cierre Z filtra por (session_id, status) y no había índice ninguno.
    op.create_index(
        "ix_orders_session_status", "orders", ["session_id", "status"]
    )
    # La comprobación de «¿esto ya está devuelto?» recorre por aquí.
    op.create_index("ix_orders_refunds_order_id", "orders", ["refunds_order_id"])
    # FK sin índice: en PostgreSQL, tocar una familia recorría productos entero.
    op.create_index("ix_products_category_id", "products", ["category_id"])

    # --- Unicidad que faltaba ----------------------------------------------
    # El número impreso del ticket es el identificador que ve el cliente.
    op.drop_index("ix_orders_ticket_full_number", table_name="orders")
    op.create_index(
        "uq_orders_ticket_full_number",
        "orders",
        ["ticket_full_number"],
        unique=True,
    )
    # Dos cierres Z con el mismo número rompen la correlatividad del libro.
    op.create_index(
        "uq_cash_sessions_z_number", "cash_sessions", ["z_number"], unique=True
    )
    # Dos platos del día para la misma fecha: la carta mostraba uno al azar.
    op.drop_index("ix_daily_specials_day", table_name="daily_specials")
    op.create_index(
        "uq_daily_specials_day", "daily_specials", ["day"], unique=True
    )

    # Una sola caja abierta. Un índice parcial sobre `closed_at` no sirve:
    # en SQL dos NULL son distintos entre sí y no colisionan. Hay que indexar
    # una expresión constante y restringir el índice a las filas abiertas.
    op.execute(
        "CREATE UNIQUE INDEX uq_cash_sessions_abierta "
        "ON cash_sessions ((closed_at IS NULL)) WHERE closed_at IS NULL"
    )

    # --- Estados válidos ----------------------------------------------------
    for table, name, column, values in CHECKS:
        with op.batch_alter_table(table) as batch:
            batch.create_check_constraint(name, _in_clause(column, values))

    # Un ticket cobrado sin número es una factura sin numerar.
    with op.batch_alter_table("orders") as batch:
        batch.create_check_constraint(
            "ck_orders_numerado",
            "status = 'open' OR "
            "(ticket_series IS NOT NULL AND ticket_number IS NOT NULL)",
        )

    # El signo del movimiento tiene que corresponder a su tipo. `correction`
    # queda libre a propósito: es el único al que tiene sentido.
    with op.batch_alter_table("cash_movements") as batch:
        batch.create_check_constraint(
            "ck_cash_movements_signo",
            "(kind IN ('deposit_out', 'withdrawal') AND amount_cents <= 0) OR "
            "(kind IN ('deposit_in', 'float_in') AND amount_cents >= 0) OR "
            "kind = 'correction'",
        )

    # Una línea de cero unidades no existe; el signo negativo es la devolución.
    with op.batch_alter_table("order_lines") as batch:
        batch.create_check_constraint("ck_order_lines_cantidad", "quantity <> 0")


def downgrade() -> None:
    with op.batch_alter_table("order_lines") as batch:
        batch.drop_constraint("ck_order_lines_cantidad", type_="check")
    with op.batch_alter_table("cash_movements") as batch:
        batch.drop_constraint("ck_cash_movements_signo", type_="check")
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("ck_orders_numerado", type_="check")

    for table, name, _column, _values in reversed(CHECKS):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="check")

    op.execute("DROP INDEX uq_cash_sessions_abierta")

    op.drop_index("uq_daily_specials_day", table_name="daily_specials")
    op.create_index("ix_daily_specials_day", "daily_specials", ["day"])
    op.drop_index("uq_cash_sessions_z_number", table_name="cash_sessions")
    op.drop_index("uq_orders_ticket_full_number", table_name="orders")
    op.create_index("ix_orders_ticket_full_number", "orders", ["ticket_full_number"])

    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_index("ix_orders_refunds_order_id", table_name="orders")
    op.drop_index("ix_orders_session_status", table_name="orders")

    op.drop_index("ix_order_lines_refunds_line_id", table_name="order_lines")
    with op.batch_alter_table("order_lines") as batch:
        batch.drop_constraint("fk_order_lines_refunds_line_id", type_="foreignkey")
        batch.drop_column("refunds_line_id")
