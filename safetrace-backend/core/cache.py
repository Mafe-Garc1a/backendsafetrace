"""Sesiones y permisos en Redis (Integración Redis v2, secciones 6.1, 6.2 y 6.4).

Redis nunca guarda un dato que no esté también en MongoDB; todas las claves vencen. Cada función devuelve
None o False si Redis no está disponible, y quien llama consulta MongoDB.
"""

from core.config import settings
from core.redis_cliente import clave, tolerante


def _segundos_sesion() -> int:
    return settings.minutos_sesion * 60


# --- Sesiones (RNF-11) ------------------------------------------------------------


def sesion_guardar(token_hash: str, usuario_id: object, renovada_en_mongo: float) -> None:
    """Guarda la sesión y la agrega al conjunto de sesiones del usuario.

    El valor es `<usuario_id>|<segundos epoch de la última renovación en MongoDB>`: así, con una sola
    lectura, se sabe si toca renovar el respaldo en MongoDB (cada 5 minutos como máximo).
    """

    def operacion(r):
        conjunto = clave("usuario_sesiones", usuario_id)
        tuberia = r.pipeline()
        tuberia.set(clave("sesion", token_hash), f"{usuario_id}|{int(renovada_en_mongo)}", ex=_segundos_sesion())
        tuberia.sadd(conjunto, token_hash)
        tuberia.expire(conjunto, settings.jwt_access_token_expire_minutes * 60)
        tuberia.execute()

    tolerante(operacion, None)


def sesion_leer(token_hash: str) -> tuple[str, int] | None:
    """(id del usuario, última renovación en MongoDB), renovando el vencimiento en Redis (GETEX).

    None si Redis no conoce la sesión o no está disponible: entonces decide MongoDB.
    """
    valor = tolerante(lambda r: r.getex(clave("sesion", token_hash), ex=_segundos_sesion()), None)
    if not valor or "|" not in valor:
        return None
    usuario_id, renovada = valor.split("|", 1)
    return usuario_id, int(renovada)


def sesion_borrar(token_hash: str) -> None:
    tolerante(lambda r: r.delete(clave("sesion", token_hash)), None)


def sesiones_borrar_de_usuarios(usuarios_ids: list) -> None:
    """Borra todas las sesiones de esos usuarios (desactivar, cambiar rol, supresión, recuperación)."""

    def operacion(r):
        for usuario_id in usuarios_ids:
            conjunto = clave("usuario_sesiones", usuario_id)
            hashes = r.smembers(conjunto)
            if hashes:
                r.delete(*[clave("sesion", h) for h in hashes])
            r.delete(conjunto)

    tolerante(operacion, None)


# --- Permisos (RNF-08, RF-74) -------------------------------------------------------


def permiso_leer(rol: str, modulo: str, accion: str) -> bool | None:
    """True o False si Redis lo tiene; None si hay que consultar MongoDB."""
    valor = tolerante(lambda r: r.get(clave("permiso", rol, modulo, accion)), None)
    return None if valor is None else valor == "1"


def permiso_guardar(rol: str, modulo: str, accion: str, permitido: bool) -> None:
    tolerante(
        lambda r: r.set(
            clave("permiso", rol, modulo, accion), "1" if permitido else "0", ex=settings.permisos_cache_segundos
        ),
        None,
    )


def permisos_invalidar() -> None:
    """Borra todas las claves permiso:*. Se llama después de escribir en permisos o en el estado de un módulo."""

    def operacion(r):
        claves = list(r.scan_iter(match=clave("permiso", "*"), count=500))
        if claves:
            r.delete(*claves)

    tolerante(operacion, None)
