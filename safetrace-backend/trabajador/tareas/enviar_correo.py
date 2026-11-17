"""ENVIAR_CORREO: envía un correo y actualiza su estado (RF-37, RF-69, RF-70, RF-73).

Dos casos:
- `notificacion_id`: correo de una notificación; se marca ENVIADA o FALLIDA en `notificaciones`.
- `recuperacion_id`: enlace de recuperación de contraseña (RF-73). No es una notificación: el token
  se genera aquí, justo antes de enviar, y solo su huella queda en MongoDB (Diseño DataBase v3, 6.3).
"""

from app.crud import notificaciones as crud_notificaciones
from app.crud import usuarios as crud_usuarios
from core import email
from core.config import settings

PLANTILLA_RECUPERACION = "RECUPERAR_CONTRASENA"


def ejecutar(db, tarea: dict) -> None:
    if "recuperacion_id" in tarea["datos"]:
        _enviar_recuperacion(db, tarea["datos"]["recuperacion_id"])
        return
    notificacion = crud_notificaciones.obtener_notificacion(db, tarea["datos"]["notificacion_id"])
    if notificacion is None or notificacion["estado"] == "ENVIADA":
        return
    usuario = crud_usuarios.obtener_usuario(db, notificacion["usuario_id"])
    if usuario is None or not usuario["activo"]:
        crud_notificaciones.marcar_notificacion(db, notificacion["_id"], "FALLIDA")
        return
    datos = {"referencia": notificacion["referencia"]}
    email.circuito.llamar(email.enviar, usuario["correo"], notificacion["tipo"], datos)
    crud_notificaciones.marcar_notificacion(db, notificacion["_id"], "ENVIADA")


def _enviar_recuperacion(db, recuperacion_id) -> None:
    emitido = crud_usuarios.emitir_token_recuperacion(db, recuperacion_id)
    if emitido is None:  # ya se usó, venció o la cuenta se desactivó: no hay nada que enviar
        return
    correo, token = emitido
    enlace = f"{settings.url_frontend.rstrip('/')}/recuperar-contrasena?token={token}"
    datos = {"enlace": enlace, "minutos": settings.minutos_recuperacion}
    email.circuito.llamar(email.enviar, correo, PLANTILLA_RECUPERACION, datos)


def al_fallar(db, tarea: dict, definitiva: bool) -> None:
    if definitiva and "notificacion_id" in tarea["datos"]:
        crud_notificaciones.marcar_notificacion(db, tarea["datos"]["notificacion_id"], "FALLIDA")
