"""Importa todos los modelos para que Alembic vea el metadata completo."""

from app.models.audit import AuditLog
from app.models.base import Base, Entity
from app.models.cash import CashMovement, CashSession, Deposit
from app.models.catalog import Category, DailySpecial, Product, ProductVariant
from app.models.org import Business, Device, Staff, TicketCounter
from app.models.preorders import Preorder, PreorderLine
from app.models.sales import Order, OrderLine, Payment

__all__ = [
    "AuditLog", "Base", "Business", "CashMovement", "CashSession", "Category",
    "DailySpecial", "Deposit", "Device", "Entity", "Order", "OrderLine",
    "Payment", "Preorder", "TicketCounter", "PreorderLine", "Product", "ProductVariant", "Staff",
]
