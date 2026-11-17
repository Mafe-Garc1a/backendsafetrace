"""Conexión a Redis (Integración Redis v2, sección 8; RC-2026-010).

Redis acelera y protege; MongoDB decide. Si REDIS_URL está vacío (pruebas unitarias) o Redis no responde,
cada operación devuelve su valor por defecto y la API sigue con MongoDB (degradación controlada, sección 12).
"""

import time
from collections.abc import Callable
from typing import Any

from core.config import settings
from core.registro import obtener_logger

log = obtener_logger("redis")

SEGUNDOS_PAUSA = 15  # tras un fallo, no se vuelve a intentar durante este tiempo
SEGUNDOS_TIMEOUT = 1.0

_cliente = None
_creado = False
_pausado_hasta = 0.0


def obtener_redis():
    """Cliente de Redis o None (sin REDIS_URL, sin la librería o en pausa tras un fallo)."""
    global _cliente, _creado
    if time.monotonic() < _pausado_hasta:
        return None
    if not _creado:
        _creado = True
        if settings.redis_url:
            import redis  # solo se importa si hay Redis configurado

            _cliente = redis.Redis.from_url(
                settings.redis_url,
                socket_timeout=SEGUNDOS_TIMEOUT,
                socket_connect_timeout=SEGUNDOS_TIMEOUT,
                decode_responses=True,
            )
    return _cliente


def usar_cliente(cliente) -> None:
    """Fija el cliente (las pruebas usan fakeredis). None desactiva Redis."""
    global _cliente, _creado, _pausado_hasta
    _cliente, _creado, _pausado_hasta = cliente, True, 0.0


def clave(*partes: object) -> str:
    """Clave con prefijo: safetrace:sesion:<hash>."""
    return ":".join([settings.redis_prefijo, *(str(p) for p in partes)])


def tolerante[T](operacion: Callable[[Any], T], por_defecto: T) -> T:
    """Ejecuta `operacion(cliente)`; si no hay Redis o falla, devuelve `por_defecto` y pausa Redis 15 s."""
    global _pausado_hasta
    cliente = obtener_redis()
    if cliente is None:
        return por_defecto
    try:
        return operacion(cliente)
    except Exception as e:  # cualquier error de Redis: se sigue con MongoDB
        _pausado_hasta = time.monotonic() + SEGUNDOS_PAUSA
        log.warning("Redis no respondió (%s); se sigue con MongoDB %s s", type(e).__name__, SEGUNDOS_PAUSA)
        return por_defecto
