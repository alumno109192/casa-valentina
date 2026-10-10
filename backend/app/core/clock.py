"""La jornada del negocio, en hora local.

Todo se guarda en UTC; lo que es local es la *interpretación*. Un asador cierra
pasada la medianoche, así que cortar el día en UTC parte la jornada por la mitad
en horario de verano: un ticket de las 00:30 del día 1 en Madrid es las 22:30
UTC del día 31, y caería en el mes (o el año) anterior.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Coincide con Business.timezone, que es el dato editable del negocio. Se deja
# aquí como respaldo para el código que no tiene la fila a mano.
DEFAULT_TZ = "Europe/Madrid"


def business_tz(name: str | None = None) -> ZoneInfo:
    return ZoneInfo(name or DEFAULT_TZ)


def today(tz: str | None = None) -> date:
    """El día de hoy según el reloj del local, no según UTC."""
    return datetime.now(business_tz(tz)).date()


def local_year(moment: datetime, tz: str | None = None) -> int:
    """El año al que pertenece un instante en hora local.

    Importa en Nochevieja: un cobro a las 00:30 del 1 de enero no debe salir
    numerado con el año anterior.
    """
    return moment.astimezone(business_tz(tz)).year


def day_range(day: date, tz: str | None = None) -> tuple[datetime, datetime]:
    """Intervalo UTC [inicio, fin) de un día natural del local.

    Se devuelve medio abierto a propósito: `>= inicio` y `< fin` no deja fuera
    el último microsegundo ni duplica el primero del día siguiente.
    """
    zone = business_tz(tz)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start, end
