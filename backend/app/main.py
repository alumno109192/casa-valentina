"""TPV Casa Valentina — API.

El backend corre en el mini-PC del local y sirve al TPV, al panel y a la carta
pública por la red del establecimiento. Que esté en el local es lo que permite
seguir cobrando cuando se cae internet.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, cash, catalog, preorders, sales
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="TPV, carta y encargos del Asador Casa Valentina.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(sales.router, prefix="/api")
app.include_router(cash.router, prefix="/api")
app.include_router(preorders.router, prefix="/api")


@app.get("/api/health", tags=["estado"])
def health() -> dict[str, str]:
    """Lo consulta el TPV para pintar el indicador de conexión."""
    return {"status": "ok", "environment": settings.environment}
