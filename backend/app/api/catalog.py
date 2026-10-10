"""Catálogo: lectura para el TPV y la carta, edición para el panel."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentStaff, DbSession, Owner
from app.models.audit import AuditLog
from app.models.catalog import Category, DailySpecial, Product, ProductVariant
from app.schemas.catalog import (
    CategoryIn,
    CategoryOut,
    DailySpecialIn,
    DailySpecialOut,
    MenuCategory,
    ProductIn,
    ProductOut,
    ProductPatch,
    VariantIn,
)

router = APIRouter(prefix="/catalog", tags=["catálogo"])


def _tree(db: DbSession, channel: str) -> list[MenuCategory]:
    """Familias con sus productos para un canal ('pos' o 'menu')."""
    cat_visible = Category.show_in_pos if channel == "pos" else Category.show_in_menu
    prod_visible = Product.show_in_pos if channel == "pos" else Product.show_in_menu

    categories = db.scalars(
        select(Category)
        .where(cat_visible, ~Category.archived)
        .order_by(Category.sort_order, Category.name)
    ).all()

    stmt = (
        select(Product)
        # Una variante archivada seguía apareciendo en la botonera y se podía
        # vender al precio viejo, justo lo que el archivado quiere evitar.
        .options(selectinload(Product.variants.and_(~ProductVariant.archived)))
        .where(prod_visible, ~Product.archived)
        .order_by(Product.sort_order, Product.name)
    )
    if channel == "menu":
        # En la carta pública lo agotado no se ofrece; en el TPV sí aparece,
        # atenuado, para que el cajero sepa que existe.
        stmt = stmt.where(Product.is_available)

    products = db.scalars(stmt).all()

    by_category: dict[uuid.UUID, list[Product]] = {}
    for product in products:
        by_category.setdefault(product.category_id, []).append(product)

    return [
        MenuCategory(
            **CategoryOut.model_validate(category).model_dump(),
            products=[
                ProductOut.model_validate(p) for p in by_category.get(category.id, [])
            ],
        )
        for category in categories
    ]


@router.get("/pos", response_model=list[MenuCategory])
def catalog_for_pos(db: DbSession) -> list[MenuCategory]:
    """Botonera completa. El TPV la guarda en local para trabajar sin red."""
    return _tree(db, "pos")


@router.get("/menu", response_model=list[MenuCategory])
def catalog_for_menu(db: DbSession) -> list[MenuCategory]:
    """Carta pública del QR. Sin autenticación y de solo lectura."""
    return _tree(db, "menu")


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: DbSession) -> list[CategoryOut]:
    rows = db.scalars(
        select(Category).where(~Category.archived).order_by(Category.sort_order)
    ).all()
    return [CategoryOut.model_validate(c) for c in rows]


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, db: DbSession, _: Owner) -> CategoryOut:
    category = Category(**data.model_dump())
    db.add(category)
    db.flush()
    return CategoryOut.model_validate(category)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductIn, db: DbSession, _: Owner) -> ProductOut:
    payload = data.model_dump(exclude={"variants"})
    product = Product(**payload)

    variants = data.variants or [VariantIn(name="Ración", price_cents=0, is_default=True)]
    if not any(v.is_default for v in variants):
        variants[0].is_default = True
    for position, variant in enumerate(variants):
        product.variants.append(
            ProductVariant(**variant.model_dump() | {"sort_order": position})
        )

    db.add(product)
    db.flush()
    return ProductOut.model_validate(product)


@router.patch("/products/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: uuid.UUID, data: ProductPatch, db: DbSession, staff: CurrentStaff
) -> ProductOut:
    """Edición parcial.

    El cajero solo puede marcar un producto como agotado; el resto de campos
    exige permisos de dueño y queda en la auditoría.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "producto no encontrado")

    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return ProductOut.model_validate(product)

    if staff.role != "owner" and set(changes) - {"is_available"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "solo el dueño puede cambiar el catálogo"
        )

    before = {field: getattr(product, field) for field in changes}
    for field, value in changes.items():
        setattr(product, field, value)

    db.add(
        AuditLog(
            staff_id=staff.id,
            action="product_change",
            entity="product",
            entity_id=product.id,
            payload={"before": before, "after": changes},
        )
    )
    db.flush()
    return ProductOut.model_validate(product)


@router.put("/products/{product_id}/variants", response_model=ProductOut)
def replace_variants(
    product_id: uuid.UUID, variants: list[VariantIn], db: DbSession, staff: Owner
) -> ProductOut:
    """Sustituye las variantes y sus precios.

    Las variantes se archivan en lugar de borrarse: los tickets antiguos
    apuntan a ellas. El precio del ticket ya emitido no cambia, porque está
    copiado en la línea.
    """
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "producto no encontrado")

    before = [
        {"name": v.name, "price_cents": v.price_cents}
        for v in product.variants
        if not v.archived
    ]
    by_name = {v.name: v for v in product.variants}
    incoming = {v.name for v in variants}

    for position, data in enumerate(variants):
        existing = by_name.get(data.name)
        if existing is not None:
            existing.price_cents = data.price_cents
            existing.is_default = data.is_default
            existing.sort_order = position
            existing.archived = False
        else:
            product.variants.append(
                ProductVariant(**data.model_dump() | {"sort_order": position})
            )

    for variant in product.variants:
        if variant.name not in incoming:
            variant.archived = True

    db.add(
        AuditLog(
            staff_id=staff.id,
            action="price_change",
            entity="product",
            entity_id=product.id,
            payload={
                "before": before,
                "after": [
                    {"name": v.name, "price_cents": v.price_cents} for v in variants
                ],
            },
        )
    )
    db.flush()
    return ProductOut.model_validate(product)


@router.get("/daily-special", response_model=DailySpecialOut | None)
def get_daily_special(db: DbSession, day: date | None = None) -> DailySpecialOut | None:
    target = day or date.today()
    special = db.scalars(
        select(DailySpecial).where(DailySpecial.day == target)
    ).first()
    return DailySpecialOut.model_validate(special) if special else None


@router.put("/daily-special", response_model=DailySpecialOut)
def set_daily_special(
    data: DailySpecialIn, db: DbSession, _: CurrentStaff
) -> DailySpecialOut:
    """El plato del día se edita también desde el TPV, no solo del panel."""
    special = db.scalars(
        select(DailySpecial).where(DailySpecial.day == data.day)
    ).first()
    if special is None:
        special = DailySpecial(**data.model_dump())
        db.add(special)
    else:
        for field, value in data.model_dump().items():
            setattr(special, field, value)
    db.flush()
    return DailySpecialOut.model_validate(special)
