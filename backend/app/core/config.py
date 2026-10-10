"""Configuración por entorno. Se lee de .env (ver .env.example)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    jwt_secret: str = "clave-de-desarrollo-cambiar-en-produccion-32b"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
