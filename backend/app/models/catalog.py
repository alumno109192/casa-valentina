"""Catálogo: familias, productos y variantes.

La media ración es una variante del producto, no un producto aparte.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Entity


class Category(Entity):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(20), default="#9e9e9e")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    show_in_pos: Mapped[bool] = mapped_column(Boolean, default=True)
    show_in_menu: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Entity):
    __tablename__ = "products"

    category_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("categories.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    short_name: Mapped[str] = mapped_column(String(40))  # texto del botón
    description: Mapped[str | None] = mapped_column(String(500))
    image_url: Mapped[str | None] = mapped_column(String(500))
    vat_rate: Mapped[int] = mapped_column(Integer, default=10)  # porcentaje entero
    is_open_price: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)  # agotado hoy
    show_in_pos: Mapped[bool] = mapped_column(Boolean, default=True)
    show_in_menu: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    category: Mapped[Category] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan",
        order_by="ProductVariant.sort_order",
    )


class ProductVariant(Entity):
    """'Ración' / 'Media' / '0,33 L'. Todo producto tiene al menos una."""

    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_variant_name"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("products.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(50))
    price_cents: Mapped[int] = mapped_column(Integer)  # precio con IVA incluido
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    product: Mapped[Product] = relationship(back_populates="variants")


class DailySpecial(Entity):
    __tablename__ = "daily_specials"
    __table_args__ = (
        # Una sugerencia por día: con dos, la carta mostraba una al azar.
        Index("uq_daily_specials_day", "day", unique=True),
    )

    day: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(String(500))
    price_cents: Mapped[int | None] = mapped_column(Integer)
    product_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("products.id"))
