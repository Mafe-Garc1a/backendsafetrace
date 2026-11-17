"""Límite de intentos con Redis (Integración Redis v2, sección 6.3; RC-2026-010, RNF-40 propuesto).

Contadores con ventana fija. Superado el límite, la API responde 429 con Retry-After. Sin Redis no hay
límite: la API sigue funcionando (degradación controlada). Las IP viven como máximo una hora y el correo
nunca aparece en claro: se guarda su huella (RNF-20).
"""

import hashlib

from fastapi import HTTPException, Request

from core.config import settings
from core.redis_cliente import clave, tolerante


def ip_de(request: Request) -> str:
    """IP del cliente. Detrás del proxy del hosting, uvicorn la toma de X-Forwarded-For (--proxy-headers)."""
    return request.client.host if request.client else "desconocida"


def _huella(correo: str) -> str:
    return hashlib.sha256(correo.strip().lower().encode()).hexdigest()[:16]


def _demasiadas(segundos: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Demasiadas solicitudes; intente más tarde",
        headers={"Retry-After": str(segundos)},
    )


def _contar(nombre: str, ventana: int) -> int:
    """Suma 1 al contador; la ventana empieza con la primera solicitud. 0 si no hay Redis."""

    def operacion(r):
        tuberia = r.pipeline()
        tuberia.incr(nombre)
        tuberia.expire(nombre, ventana, nx=True)
        return tuberia.execute()[0]

    return tolerante(operacion, 0)


def limitar_por_ip(tipo: str, maximo: int, ventana: int):
    """Dependencia de FastAPI: más de `maximo` solicitudes por IP en `ventana` segundos → 429."""

    def _dependencia(request: Request) -> None:
        if _contar(clave("limite", tipo, ip_de(request)), ventana) > maximo:
            raise _demasiadas(ventana)

    return _dependencia


def limite_publico():
    """Vista pública del enlace: 60 solicitudes por minuto por IP."""
    return limitar_por_ip("publico", settings.publico_max_por_minuto, 60)


def limite_verificar():
    """Verificación de constancias (RF-58): 30 por minuto por IP."""
    return limitar_por_ip("verificar", settings.verificar_max_por_minuto, 60)


def limite_recuperar():
    """Solicitud de recuperación de contraseña (RF-73): 5 por hora por IP."""
    return limitar_por_ip("recuperar", settings.recuperar_max_por_hora_ip, 3600)


# --- Inicio de sesión: 5 fallos por IP y correo, 30 por IP, en 15 minutos -----------------


def _claves_login(ip: str, correo: str) -> tuple[str, str]:
    return clave("login", ip, _huella(correo)), clave("login_ip", ip)


def login_bloqueado(ip: str, correo: str) -> None:
    """Se revisa ANTES de bcrypt: protege las contraseñas y el procesador. Lanza 429 si está bloqueado."""
    par, solo_ip = _claves_login(ip, correo)
    valores = tolerante(lambda r: r.mget(par, solo_ip), [None, None])
    fallos_par = int(valores[0] or 0)
    fallos_ip = int(valores[1] or 0)
    if fallos_par >= settings.login_max_intentos or fallos_ip >= settings.login_max_intentos_ip:
        raise _demasiadas(settings.login_ventana_segundos)


def login_fallido(ip: str, correo: str) -> None:
    par, solo_ip = _claves_login(ip, correo)
    _contar(par, settings.login_ventana_segundos)
    _contar(solo_ip, settings.login_ventana_segundos)


def login_exitoso(ip: str, correo: str) -> None:
    """Un acierto reinicia solo el contador del par IP y correo, no el de la IP."""
    par, _ = _claves_login(ip, correo)
    tolerante(lambda r: r.delete(par), None)
