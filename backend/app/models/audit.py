"""Registro de acciones sensibles: anulaciones, caja, cambios de precio."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, Entity, JSONType


class AuditLog(Entity):
    __tablename__ = "audit_log"

    staff_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("staff.id"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("devices.id"))
    action: Mapped[str] = mapped_column(String(50), index=True)
    entity: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    payload: Mapped[dict | None] = mapped_column(JSONType)
