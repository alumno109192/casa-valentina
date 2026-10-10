"""Esquemas del catálogo. Los precios viajan en céntimos enteros."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VariantOut(ORMModel):
    id: uuid.UUID
    name: str
    price_cents: int
    sort_order: int
    is_default: bool


class VariantIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    price_cents: int = Field(ge=0)
    sort_order: int = 0
    is_default: bool = False


class ProductOut(ORMModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    short_name: str
    description: str | None = None
    image_url: str | None = None
    vat_rate: int
    is_open_price: bool
    is_available: bool
    show_in_pos: bool
    show_in_menu: bool
    sort_order: int
    variants: list[VariantOut] = []


class ProductIn(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=150)
    short_name: str = Field(min_length=1, max_length=40)
    description: str | None = None
    image_url: str | None = None
    vat_rate: int = 10
    is_open_price: bool = False
    is_available: bool = True
    show_in_pos: bool = True
    show_in_menu: bool = True
    sort_order: int = 0
    variants: list[VariantIn] = []


class ProductPatch(BaseModel):
    """Edición parcial. El TPV solo usa `is_available` (agotado hoy)."""

    name: str | None = None
    short_name: str | None = None
    description: str | None = None
    vat_rate: int | None = None
    is_available: bool | None = None
    show_in_pos: bool | None = None
    show_in_menu: bool | None = None
    sort_order: int | None = None
    archived: bool | None = None


class CategoryOut(ORMModel):
    id: uuid.UUID
    name: str
    color: str
    sort_order: int
    show_in_pos: bool
    show_in_menu: bool


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#9e9e9e"
    sort_order: int = 0
    show_in_pos: bool = True
    show_in_menu: bool = True


class DailySpecialOut(ORMModel):
    id: uuid.UUID
    day: date
    title: str
    description: str | None = None
    price_cents: int | None = None


class DailySpecialIn(BaseModel):
    day: date
    title: str = Field(min_length=1, max_length=150)
    description: str | None = None
    price_cents: int | None = None
    product_id: uuid.UUID | None = None


class MenuCategory(CategoryOut):
    """Familia con sus productos, para la carta pública y la botonera."""

    products: list[ProductOut] = []
