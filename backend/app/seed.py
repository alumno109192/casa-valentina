"""Catálogo inicial del Asador Casa Valentina.

AVISO SOBRE LOS PRECIOS
-----------------------
Los importes de este fichero son PROVISIONALES: sirven para poder probar la
botonera, los informes y el cierre de caja de punta a punta. Hay que
sustituirlos por la exportación de Dish (fase 0 del plan). La media ración se
ha calculado como el 60 % de la ración redondeado a múltiplos de 0,05 €, que es
una convención, no un dato del cliente.

El IVA está al 10 % en comida y bebida, y al 21 % en bolsas y envases.
Pendiente de confirmar con la gestoría.

Uso:
    python -m app.seed            # siembra si la base está vacía
    python -m app.seed --reset    # borra el catálogo y lo vuelve a sembrar
"""

from __future__ import annotations

import sys

from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.core.security import hash_pin
from app.models.catalog import Category, Product, ProductVariant
from app.models.org import Business, Device, Staff

# (familia, color, [(nombre, nombre_corto, tiene_media, precio_racion_cents)])
RACION = True
SIMPLE = False

CATALOG: list[tuple[str, str, list[tuple[str, str, bool, int]]]] = [
    ("Picar", "#8d6e63", [
        ("Empanadillas", "Empanadillas", RACION, 700),
        ("Huevos bechamel", "Huevos bech.", RACION, 700),
        ("Croquetas", "Croquetas", RACION, 700),
        ("Minibombas", "Minibombas", RACION, 750),
        ("Sepia", "Sepia", RACION, 1100),
        ("Fingers de pollo", "Fingers", RACION, 700),
        ("Pechuga villeroy", "Villeroy", RACION, 800),
        ("Alioli", "Alioli", SIMPLE, 250),
        ("Tortilla", "Tortilla", SIMPLE, 800),
        ("Salpicón de marisco", "Salpicón", RACION, 1200),
        ("Oreja en salsa", "Oreja", RACION, 900),
        ("Patatas panadera", "Panadera", RACION, 600),
        ("Alitas de pollo", "Alitas", RACION, 700),
        ("Mejillones tigre", "Mej. tigre", RACION, 800),
        ("Pimientos verdes", "Pim. verdes", RACION, 600),
        ("Calamares a la romana", "Calamares", RACION, 1000),
        ("Gambardinas", "Gambardinas", RACION, 900),
    ]),
    ("Primeros", "#43a047", [
        ("Alcachofas", "Alcachofas", RACION, 800),
        ("Brócoli", "Brócoli", RACION, 700),
        ("Champiñones y jamón", "Champi jamón", RACION, 800),
        ("Fabada", "Fabada", RACION, 800),
        ("Fideos chinos", "Fideos chinos", RACION, 700),
        ("Guiso de patatas", "Guiso patatas", RACION, 700),
        ("Huevos rellenos", "Huevos rell.", RACION, 700),
        ("Judías verdes", "Judías verdes", RACION, 700),
        ("Migas", "Migas", RACION, 800),
        ("Pasta carbonara", "Carbonara", RACION, 750),
        ("Pimiento de carne", "Pim. carne", RACION, 800),
        ("Pisto manchego", "Pisto", RACION, 700),
        ("Revuelto de setas", "Rev. setas", RACION, 850),
        ("Sarmale", "Sarmale", RACION, 900),
        ("Paella", "Paella", RACION, 900),
        ("Guisantes y jamón", "Guis. jamón", RACION, 800),
        ("Pimientos del piquillo", "Piquillo", RACION, 800),
        ("Arroz tres delicias", "3 delicias", RACION, 700),
        ("Asadillo", "Asadillo", RACION, 750),
        ("Lentejas", "Lentejas", RACION, 700),
        ("Macarrones", "Macarrones", RACION, 700),
        ("Berenjenas", "Berenjenas", RACION, 800),
        ("Fideuá", "Fideuá", RACION, 900),
    ]),
    ("Carne", "#c62828", [
        ("Cachopo", "Cachopo", RACION, 1400),
        ("Carcamusas", "Carcamusas", RACION, 900),
        ("Codillo asado", "Codillo", RACION, 1200),
        ("Costilla asada", "Costilla", RACION, 1100),
        ("Filetes rusos", "Filetes rusos", RACION, 800),
        ("Hígados en salsa", "Hígados", RACION, 800),
        ("Magro con tomate", "Magro tomate", RACION, 850),
        ("Pollo al limón", "Pollo limón", RACION, 900),
        ("Pollo al curry", "Pollo curry", RACION, 900),
        ("Pollo a la cerveza", "Pollo cerveza", RACION, 900),
        ("Pollo al ajillo", "Pollo ajillo", RACION, 900),
        ("Venado en salsa", "Venado", RACION, 1200),
        ("Lasaña", "Lasaña", RACION, 900),
        ("Albóndigas en salsa", "Albóndigas", RACION, 850),
        ("Escalope de pollo", "Escalope", RACION, 800),
        ("Carrillada de cerdo", "Carrillada", RACION, 1200),
    ]),
    ("Asados y pescado", "#6d4c41", [
        ("Pierna de cordero", "Cordero", SIMPLE, 2200),
        ("Salmón con patatas", "Salmón", SIMPLE, 1200),
        ("Merluza", "Merluza", SIMPLE, 1100),
    ]),
    ("Pollo", "#f9a825", [
        ("Pollo asado", "POLLO", SIMPLE, 1200),
        ("Medio pollo asado", "1/2 POLLO", SIMPLE, 650),
        ("Menú 1", "MENÚ 1", SIMPLE, 1500),
        ("Menú 2", "MENÚ 2", SIMPLE, 1800),
        ("Menú 3", "MENÚ 3", SIMPLE, 2200),
        ("Pan", "Pan", SIMPLE, 100),
    ]),
    ("Ensaladas", "#7cb342", [
        ("Ensalada rusa", "Rusa", RACION, 700),
        ("Ensalada campera", "Campera", RACION, 700),
        ("Ensalada de garbanzos", "Garbanzos", RACION, 700),
        ("Ensalada de pasta", "Pasta", RACION, 700),
        ("Ensalada mixta", "Mixta", RACION, 650),
    ]),
    ("Menú del día", "#00897b", [
        ("Menú del día", "MENÚ DÍA", SIMPLE, 1200),
    ]),
    ("Postre", "#ec407a", [
        ("Flan casero", "Flan", SIMPLE, 250),
        ("Pudin", "Pudin", SIMPLE, 250),
        ("Torrijas", "Torrijas", SIMPLE, 250),
        ("Postre casero", "Postre casero", SIMPLE, 250),
        ("Natillas", "Natillas", SIMPLE, 250),
        ("Arroz con leche", "Arroz leche", SIMPLE, 250),
        ("Leche frita", "Leche frita", SIMPLE, 250),
    ]),
]

# Productos con variantes propias que no son ración/media
SIZED: list[tuple[str, str, str, int, list[tuple[str, int]]]] = [
    # (familia, nombre, nombre_corto, iva, [(variante, precio)])
    ("Pollo", "Patatas", "Patatas", 10, [("Mediana", 350), ("Grande", 450)]),
    ("Postre", "Tarta", "Tarta", 10, [("Porción", 300), ("Entera", 1800)]),
    ("Bebidas", "Agua", "Agua", 10, [("0,5 L", 100), ("1,5 L", 150)]),
    ("Bebidas", "Cerveza", "Cerveza", 10, [("0,33 L", 150), ("0,5 L", 200), ("1 L", 300)]),
    ("Bebidas", "Coca-Cola", "Coca-Cola", 10, [("0,33 L", 150), ("2 L", 300)]),
    ("Bebidas", "Fanta", "Fanta", 10, [("2 L", 300)]),
    ("Bebidas", "Vino", "Vino", 10, [("Botella", 500)]),
    ("Varios", "Bolsa", "Bolsa", 21, [("Unidad", 15)]),
    ("Varios", "Envase", "Envase", 21, [("Unidad", 30)]),
]

CATEGORY_COLORS = {
    "Bebidas": "#1e88e5",
    "Varios": "#757575",
}


def media_price(racion_cents: int) -> int:
    """60 % de la ración redondeado a múltiplos de 0,05 €. Convención, no dato."""
    return round(racion_cents * 0.6 / 5) * 5


def seed(reset: bool = False) -> None:
    db = SessionLocal()
    try:
        if reset:
            db.execute(delete(ProductVariant))
            db.execute(delete(Product))
            db.execute(delete(Category))
            db.commit()

        if db.scalar(select(Category).limit(1)) is not None:
            print("ya hay catálogo; usa --reset para rehacerlo")
            return

        if db.scalar(select(Business).limit(1)) is None:
            db.add(
                Business(
                    legal_name="PENDIENTE DE DATOS FISCALES",
                    trade_name="Asador Casa Valentina",
                    nif="PENDIENTE",
                    legal_form="autonomo",
                    phone_whatsapp="648298706",
                    ticket_footer="¡Gracias por su visita!",
                )
            )
        if db.scalar(select(Staff).limit(1)) is None:
            # PIN de arranque, a cambiar en la primera sesión
            db.add(Staff(name="Dueño", pin_hash=hash_pin("1234"), role="owner"))
        if db.scalar(select(Device).limit(1)) is None:
            db.add(
                Device(
                    name="Mostrador",
                    kind="pos",
                    ticket_series="T",
                    is_ticket_issuer=True,
                )
            )

        categories: dict[str, Category] = {}
        order = 0
        for name, color, _ in CATALOG:
            categories[name] = Category(name=name, color=color, sort_order=order)
            order += 1
        for extra in ("Bebidas", "Varios"):
            if extra not in categories:
                categories[extra] = Category(
                    name=extra, color=CATEGORY_COLORS[extra], sort_order=order
                )
                order += 1
        for category in categories.values():
            db.add(category)
        db.flush()

        count = 0
        for category_name, _, items in CATALOG:
            for position, (name, short_name, has_half, price) in enumerate(items):
                product = Product(
                    category_id=categories[category_name].id,
                    name=name,
                    short_name=short_name,
                    vat_rate=10,
                    sort_order=position,
                )
                product.variants.append(
                    ProductVariant(
                        name="Ración", price_cents=price, is_default=True, sort_order=0
                    )
                )
                if has_half:
                    product.variants.append(
                        ProductVariant(
                            name="Media",
                            price_cents=media_price(price),
                            sort_order=1,
                        )
                    )
                db.add(product)
                count += 1

        for position, (category_name, name, short_name, vat, variants) in enumerate(SIZED):
            product = Product(
                category_id=categories[category_name].id,
                name=name,
                short_name=short_name,
                vat_rate=vat,
                sort_order=100 + position,
            )
            for index, (variant_name, price) in enumerate(variants):
                product.variants.append(
                    ProductVariant(
                        name=variant_name,
                        price_cents=price,
                        is_default=index == 0,
                        sort_order=index,
                    )
                )
            db.add(product)
            count += 1

        # Precio libre: sustituye al botón "PRODUCTO" de Dish
        libre = Product(
            category_id=categories["Varios"].id,
            name="Precio libre",
            short_name="PRECIO LIBRE",
            vat_rate=10,
            is_open_price=True,
            show_in_menu=False,
            sort_order=999,
        )
        libre.variants.append(
            ProductVariant(name="Importe", price_cents=0, is_default=True)
        )
        db.add(libre)
        count += 1

        db.commit()
        print(f"sembrado: {len(categories)} familias, {count} productos")
        print("PIN inicial del dueño: 1234 (cambiarlo antes de abrir)")
        print("PRECIOS PROVISIONALES: sustituir por la exportación de Dish")
    finally:
        db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
