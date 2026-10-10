"""Configuración por entorno. Se lee de .env (ver .env.example)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor sembrado en el repositorio: sirve para desarrollar y NUNCA para producir.
DEV_JWT_SECRET = "clave-de-desarrollo-cambiar-en-produccion-32b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="TPV_", extra="ignore"
    )

    app_name: str = "TPV Casa Valentina"
    environment: str = "dev"  # dev | prod

    # SQLite en desarrollo; en el mini-PC del local se cambia a
    # postgresql+psycopg://tpv:...@localhost/tpv sin tocar código.
    database_url: str = "sqlite:///./tpv.db"
    sql_echo: bool = False

    # Autenticación: PIN del personal -> token para el TPV
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    token_ttl_minutes: int = 60 * 14  # una jornada larga, el TPV no debe caducar en servicio
    max_pin_attempts: int = 5
    pin_lockout_minutes: int = 5

    # El TPV y la carta se sirven desde la red local del establecimiento
    cors_origins: list[str] = [
        "http://localhost:4200", "http://localhost:4300", "http://localhost:4400",
        "capacitor://localhost", "http://localhost",
    ]

    default_vat_rate: int = 10
    default_ticket_series: str = "T"

    # Tipos de IVA que el negocio puede aplicar. Cualquier otro se rechaza en la
    # frontera: un desglose con un tipo inventado no lo acepta la AEAT.
    allowed_vat_rates: tuple[int, ...] = (0, 4, 10, 21)

    # Por encima de este importe la factura simplificada no basta (hostelería,
    # art. 4.2 RD 1619/2012). Pendiente de confirmar con la gestoría.
    simplified_invoice_limit_cents: int = 300_000

    @model_validator(mode="after")
    def _produccion_exige_secreto_propio(self) -> "Settings":
        """En producción no se arranca con la clave de desarrollo.

        Sin esto, instalar el mini-PC copiando el repositorio deja el secreto
        del repositorio en uso: cualquiera en la red del local podría firmarse
        un token de dueño.
        """
        if self.environment != "prod":
            return self
        if self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError(
                "TPV_JWT_SECRET sigue siendo la clave de desarrollo. "
                "Genera una propia antes de arrancar en producción."
            )
        if len(self.jwt_secret.encode()) < 32:
            raise ValueError("TPV_JWT_SECRET debe tener al menos 32 bytes")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
