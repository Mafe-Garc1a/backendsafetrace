"""Acceso a datos y reglas de A · Cuentas y administración (RF-01 a RF-09).

Colecciones de las que es dueño: usuarios, sesiones, recuperaciones_contrasena, solicitudes_supresion.
Solo este archivo las escribe.

Reglas clave:
- La contraseña se guarda con hash y sal (RNF-09).
- La sesión vence a los 30 minutos sin actividad (RNF-11). Vive en Redis y MongoDB guarda el respaldo,
  que se renueva como máximo cada 5 minutos (Diseño DataBase v3, 6.2; Integración Redis v2, 6.1).
- Solo se piden los datos necesarios (RNF-17).
"""

import secrets
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import auditoria
from app.crud import notificaciones as crud_notificaciones
from app.schemas.usuarios import UsuarioCreate
from core import cache
from core.config import settings
from core.errores import ErrorNegocio
from core.fechas import ahora
from core.security import hash_contrasena, hash_token

# El hash de la contraseña nunca sale de este archivo, salvo para el inicio de sesión
SIN_CONTRASENA = {"contrasena_hash": 0}


ROL_ADMINISTRADOR = "ADMINISTRADOR_GENERAL"
# Roles que el administrador general puede dar o quitar (Diseño DataBase v3, 6.1; RF-06, RF-74)
ROLES_GESTIONA_ADMINISTRADOR = frozenset({"PROPIETARIO", "PERITO"})


class EnlaceInvalido(ErrorNegocio):
    """El enlace de recuperación no existe, ya se usó o venció."""

    status = 400
    codigo = "ENLACE_INVALIDO"
    mensaje = "El enlace no es válido o ya venció. Solicite uno nuevo"


class CorreoDuplicado(ErrorNegocio):
    """Ya existe una cuenta con ese correo."""

    codigo = "CORREO_DUPLICADO"
    mensaje = "Ya existe una cuenta con ese correo"


def crear_usuario(db: Database, usuario: UsuarioCreate, rol: str) -> dict:
    """Registro con consentimiento (RF-01, RF-07). El correo se guarda en minúsculas."""
    return _insertar_usuario(
        db,
        correo=usuario.correo,
        contrasena=usuario.contrasena,
        rol=rol,
        nombre_completo=usuario.nombre_completo,
        version_politica=usuario.version_politica,
        actor=None,
    )


def crear_administrador(db: Database, nombre_completo: str, correo: str, actor: dict) -> dict:
    """El SUPERADMIN crea una cuenta de administrador general (RF-74).

    La cuenta nace con una contraseña aleatoria que nadie conoce y se envía al correo un enlace de
    recuperación (RF-73) para que el administrador elija la suya: ninguna contraseña viaja ni se guarda
    en claro. El consentimiento se registra cuando el administrador inicia sesión por primera vez
    con la versión vigente de la política [supuesto: lo confirma el PO].
    """
    documento = _insertar_usuario(
        db,
        correo=correo,
        contrasena=secrets.token_urlsafe(32),
        rol=ROL_ADMINISTRADOR,
        nombre_completo=nombre_completo,
        version_politica=None,
        actor=actor,
    )
    _crear_recuperacion(db, documento["_id"], ROL_ADMINISTRADOR)
    return documento


def _insertar_usuario(
    db: Database,
    correo: str,
    contrasena: str,
    rol: str,
    nombre_completo: str,
    version_politica: str | None,
    actor: dict | None,
) -> dict:
    correo = correo.lower()
    if db["usuarios"].find_one({"correo": correo}, {"_id": 1}):
        raise CorreoDuplicado()
    momento = ahora()
    consentimiento = (
        {"aceptado": True, "version_politica": version_politica, "fecha": momento} if version_politica else None
    )
    documento = {
        "correo": correo,
        "contrasena_hash": hash_contrasena(contrasena),
        "rol": rol,
        "nombre_completo": nombre_completo,
        "activo": True,
        "consentimiento": consentimiento,
        "schema_version": 3,
        "creado_en": momento,
        "actualizado_en": momento,
    }
    try:
        resultado = db["usuarios"].insert_one(documento)
    except DuplicateKeyError:
        raise CorreoDuplicado() from None
    documento["_id"] = resultado.inserted_id
    # Registro propio o cuenta creada por el SUPERADMIN (RF-74): la misma acción, distinto actor
    actor = actor or {"tipo": "USUARIO", "id": resultado.inserted_id, "rol": rol}
    auditoria.registrar(db, "usuarios", resultado.inserted_id, "REGISTRAR_USUARIO", actor, {"rol": rol})
    documento.pop("contrasena_hash")
    return documento


def obtener_usuario(db: Database, usuario_id: ObjectId) -> dict | None:
    """Datos básicos del usuario (sin contraseña). Lo usan todos."""
    return db["usuarios"].find_one({"_id": usuario_id}, SIN_CONTRASENA)


def obtener_usuario_por_correo(db: Database, correo: str) -> dict | None:
    """Usuario con su hash de contraseña, solo para el inicio de sesión (RF-02)."""
    return db["usuarios"].find_one({"correo": correo.lower()})


def obtener_hash_contrasena(db: Database, usuario_id: ObjectId) -> str | None:
    """Hash de la contraseña para confirmar la firma de una inspección (RF-52)."""
    usuario = db["usuarios"].find_one({"_id": usuario_id}, {"contrasena_hash": 1})
    return usuario["contrasena_hash"] if usuario else None


def listar_usuarios(db: Database, filtros: dict, saltar: int = 0, limite: int = 20) -> tuple[list[dict], int]:
    """Lista de usuarios para el administrador general (RF-04)."""
    total = db["usuarios"].count_documents(filtros)
    datos = list(db["usuarios"].find(filtros, SIN_CONTRASENA).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total


def cambiar_activo(db: Database, usuario_id: ObjectId, activo: bool, actor: dict) -> dict | None:
    """Activa o desactiva una cuenta (RF-05). Al desactivarla se cierran sus sesiones."""
    anterior = db["usuarios"].find_one_and_update(
        {"_id": usuario_id},
        {"$set": {"activo": activo, "actualizado_en": ahora()}},
        projection=SIN_CONTRASENA,
    )
    if anterior is None:
        return None
    if not activo:
        cerrar_sesiones_de(db, [usuario_id])
    auditoria.registrar(
        db, "usuarios", usuario_id, "CAMBIAR_ACTIVO", actor, {"anterior": anterior["activo"], "nuevo": activo}
    )
    return obtener_usuario(db, usuario_id)


def cambiar_rol(db: Database, usuario_id: ObjectId, rol: str, actor: dict) -> dict | None:
    """Cambia el rol (RF-06). Se cierran sus sesiones para que el nuevo rol aplique al volver a entrar."""
    anterior = db["usuarios"].find_one_and_update(
        {"_id": usuario_id},
        {"$set": {"rol": rol, "actualizado_en": ahora()}},
        projection=SIN_CONTRASENA,
    )
    if anterior is None:
        return None
    cerrar_sesiones_de(db, [usuario_id])
    auditoria.registrar(db, "usuarios", usuario_id, "CAMBIAR_ROL", actor, {"anterior": anterior["rol"], "nuevo": rol})
    return obtener_usuario(db, usuario_id)


# --- Sesiones (RF-02, RF-03, RNF-11) -----------------------------------------


def _epoch(momento: datetime) -> float:
    """Segundos epoch de una fecha de MongoDB (mongomock y PyMongo pueden devolverla sin zona)."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.timestamp()


def crear_sesion(db: Database, usuario_id: ObjectId, token_hash: str) -> None:
    """Respaldo en MongoDB y copia en Redis (Integración Redis v2, 6.1)."""
    momento = ahora()
    db["sesiones"].insert_one(
        {
            "usuario_id": usuario_id,
            "token_hash": token_hash,
            "creado_en": momento,
            "ultima_actividad": momento,
            "expira_en": momento + timedelta(minutes=settings.minutos_sesion),
        }
    )
    cache.sesion_guardar(token_hash, usuario_id, _epoch(momento))


def _renovar_en_mongo(db: Database, token_hash: str, momento: datetime) -> dict | None:
    """Extiende la sesión 30 min en MongoDB si sigue vigente; None si ya no existe o venció."""
    return db["sesiones"].find_one_and_update(
        {"token_hash": token_hash, "expira_en": {"$gt": momento}},
        {"$set": {"ultima_actividad": momento, "expira_en": momento + timedelta(minutes=settings.minutos_sesion)}},
        return_document=ReturnDocument.AFTER,
    )


def obtener_sesion_vigente(db: Database, token_hash: str) -> dict | None:
    """Sesión vigente por hash de token; extiende su vencimiento 30 min (RNF-11).

    1. Redis primero (GETEX renueva su vencimiento). Si pasaron 5 minutos o más desde la última
       renovación en MongoDB, se renueva el respaldo; si MongoDB ya no la tiene, la sesión se cerró
       mientras Redis estaba caído y se borra también de Redis.
    2. Si Redis no la conoce (reinicio o sin Redis), decide MongoDB y la sesión se vuelve a cargar en Redis.

    Se filtra también por `expira_en` porque MongoDB borra las sesiones vencidas (índice TTL)
    cada minuto, no al instante.
    """
    momento = ahora()
    espera = settings.sesion_renovar_mongo_segundos
    en_redis = cache.sesion_leer(token_hash)
    if en_redis is not None:
        usuario_id, renovada = en_redis
        if _epoch(momento) - renovada < espera:
            return {"usuario_id": ObjectId(usuario_id), "token_hash": token_hash}
        sesion = _renovar_en_mongo(db, token_hash, momento)
        if sesion is None:
            cache.sesion_borrar(token_hash)
            return None
        cache.sesion_guardar(token_hash, sesion["usuario_id"], _epoch(momento))
        return sesion

    sesion = db["sesiones"].find_one({"token_hash": token_hash, "expira_en": {"$gt": momento}})
    if sesion is None:
        return None
    if momento - _con_zona(sesion["ultima_actividad"]) >= timedelta(seconds=espera):
        sesion = _renovar_en_mongo(db, token_hash, momento)
        if sesion is None:
            return None
        cache.sesion_guardar(token_hash, sesion["usuario_id"], _epoch(momento))
    else:
        cache.sesion_guardar(token_hash, sesion["usuario_id"], _epoch(sesion["ultima_actividad"]))
    return sesion


def _con_zona(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def cerrar_sesion(db: Database, token_hash: str) -> bool:
    """Cerrar sesión borra el documento en MongoDB y la copia en Redis (RF-03)."""
    cache.sesion_borrar(token_hash)
    return db["sesiones"].delete_one({"token_hash": token_hash}).deleted_count > 0


def cerrar_sesiones_de(db: Database, usuarios_ids: list[ObjectId]) -> int:
    """Cierra todas las sesiones de esos usuarios en MongoDB y en Redis.

    Lo usan desactivar una cuenta, cambiar su rol, desactivar un rol, atender una supresión
    y restablecer la contraseña (Integración Redis v2, 6.1).
    """
    if not usuarios_ids:
        return 0
    hashes = [s["token_hash"] for s in db["sesiones"].find({"usuario_id": {"$in": usuarios_ids}}, {"token_hash": 1})]
    for token_hash in hashes:
        cache.sesion_borrar(token_hash)
    cache.sesiones_borrar_de_usuarios(usuarios_ids)
    return db["sesiones"].delete_many({"usuario_id": {"$in": usuarios_ids}}).deleted_count


def cerrar_sesiones_por_rol(db: Database, rol: str) -> int:
    """Cierra las sesiones de todos los usuarios del rol. Lo usa `crud/roles.py` al desactivar un rol."""
    ids = [u["_id"] for u in db["usuarios"].find({"rol": rol}, {"_id": 1})]
    return cerrar_sesiones_de(db, ids)


# --- Recuperación de contraseña (RF-73; Diseño DataBase v3, 6.3) -------------


def _crear_recuperacion(db: Database, usuario_id: ObjectId, rol: str) -> bool:
    """Crea el enlace y encola el correo. False si el usuario ya pidió 3 en la última hora.

    El token se genera en el trabajador justo antes de enviar el correo (`emitir_token_recuperacion`):
    así el token en claro nunca se guarda, ni siquiera en la cola de tareas. Aquí se guarda una
    huella provisional que no corresponde a ningún token entregado.
    """
    momento = ahora()
    recientes = db["recuperaciones_contrasena"].count_documents(
        {"usuario_id": usuario_id, "creado_en": {"$gt": momento - timedelta(hours=1)}}
    )
    if recientes >= settings.recuperaciones_max_por_hora:
        return False
    recuperacion_id = (
        db["recuperaciones_contrasena"]
        .insert_one(
            {
                "usuario_id": usuario_id,
                "token_hash": hash_token(secrets.token_urlsafe(32)),
                "creado_en": momento,
                "expira_en": momento + timedelta(minutes=settings.minutos_recuperacion),
                "usado_en": None,
            }
        )
        .inserted_id
    )
    crud_notificaciones.encolar_tarea(db, "ENVIAR_CORREO", {"recuperacion_id": recuperacion_id})
    actor = {"tipo": "USUARIO", "id": usuario_id, "rol": rol}
    cambios = {"recuperacion_id": recuperacion_id}
    auditoria.registrar(db, "usuarios", usuario_id, "SOLICITAR_RECUPERACION", actor, cambios)
    return True


def solicitar_recuperacion(db: Database, correo: str) -> None:
    """Si el correo existe y la cuenta está activa, se envía el enlace. La respuesta es siempre la misma."""
    usuario = db["usuarios"].find_one({"correo": correo.strip().lower(), "activo": True}, {"_id": 1, "rol": 1})
    if usuario is not None:
        _crear_recuperacion(db, usuario["_id"], usuario["rol"])


def emitir_token_recuperacion(db: Database, recuperacion_id: ObjectId) -> tuple[str, str] | None:
    """Lo llama el trabajador: genera el token, guarda solo su huella y devuelve (correo, token).

    None si el enlace ya se usó, venció o la cuenta ya no está activa. Si la tarea se reintenta,
    el token anterior deja de servir: solo vale el del último correo.
    """
    token = secrets.token_urlsafe(32)
    recuperacion = db["recuperaciones_contrasena"].find_one_and_update(
        {"_id": recuperacion_id, "usado_en": None, "expira_en": {"$gt": ahora()}},
        {"$set": {"token_hash": hash_token(token)}},
    )
    if recuperacion is None:
        return None
    usuario = db["usuarios"].find_one({"_id": recuperacion["usuario_id"], "activo": True}, {"correo": 1})
    if usuario is None:
        return None
    return usuario["correo"], token


def restablecer_contrasena(db: Database, token: str, contrasena_nueva: str) -> None:
    """Un solo uso: se marca `usado_en` en la misma operación que lo comprueba.

    Cierra todas las sesiones del usuario y deja RESTABLECER_CONTRASENA en auditoría, sin el correo (RNF-20).
    """
    momento = ahora()
    recuperacion = db["recuperaciones_contrasena"].find_one_and_update(
        {"token_hash": hash_token(token), "usado_en": None, "expira_en": {"$gt": momento}},
        {"$set": {"usado_en": momento}},
    )
    if recuperacion is None:
        raise EnlaceInvalido()
    usuario_id = recuperacion["usuario_id"]
    usuario = db["usuarios"].find_one_and_update(
        {"_id": usuario_id, "activo": True},
        {"$set": {"contrasena_hash": hash_contrasena(contrasena_nueva), "actualizado_en": momento}},
        projection={"rol": 1},
    )
    if usuario is None:
        raise EnlaceInvalido()
    cerrar_sesiones_de(db, [usuario_id])
    actor = {"tipo": "USUARIO", "id": usuario_id, "rol": usuario["rol"]}
    auditoria.registrar(
        db, "usuarios", usuario_id, "RESTABLECER_CONTRASENA", actor, {"recuperacion_id": recuperacion["_id"]}
    )


# --- Supresión de datos personales (RF-08, RF-09) ----------------------------


def solicitar_supresion(db: Database, usuario_id: ObjectId) -> dict:
    existente = db["solicitudes_supresion"].find_one({"usuario_id": usuario_id, "estado": "RECIBIDA"})
    if existente:
        return existente
    documento = {
        "usuario_id": usuario_id,
        "fecha_solicitud": ahora(),
        "estado": "RECIBIDA",
        "datos_eliminados": [],
        "datos_conservados": [],
        "atendida_por": None,
        "fecha_atencion": None,
        "schema_version": 3,
    }
    documento["_id"] = db["solicitudes_supresion"].insert_one(documento).inserted_id
    return documento


def listar_solicitudes_supresion(db: Database, estado: str | None, saltar: int, limite: int) -> tuple[list, int]:
    filtros = {"estado": estado} if estado else {}
    total = db["solicitudes_supresion"].count_documents(filtros)
    datos = list(db["solicitudes_supresion"].find(filtros).sort("fecha_solicitud", 1).skip(saltar).limit(limite))
    return datos, total


def atender_supresion(db: Database, solicitud_id: ObjectId, actor: dict) -> dict | None:
    """Anonimiza la cuenta y deja constancia de lo que se conserva y por qué (RF-09)."""
    solicitud = db["solicitudes_supresion"].find_one({"_id": solicitud_id, "estado": "RECIBIDA"})
    if solicitud is None:
        return None
    usuario_id = solicitud["usuario_id"]
    db["usuarios"].update_one(
        {"_id": usuario_id},
        {
            "$set": {
                "nombre_completo": "Usuario suprimido",
                "correo": f"suprimido-{usuario_id}@safetrace.invalid",
                "contrasena_hash": hash_contrasena(ObjectId().binary.hex()),
                "activo": False,
                "actualizado_en": ahora(),
            }
        },
    )
    cerrar_sesiones_de(db, [usuario_id])
    cambios = {
        "estado": "ATENDIDA",
        "datos_eliminados": ["nombre_completo", "correo"],
        "datos_conservados": [
            {"dato": "inmuebles, bitácora y evidencias", "motivo": "Historial del inmueble (RNF-12, RNF-16)"},
            {"dato": "inspecciones firmadas", "motivo": "Trazabilidad técnica (RNF-12)"},
            {"dato": "auditoría", "motivo": "Registro de seguridad (RNF-21)"},
        ],
        "atendida_por": actor["id"],
        "fecha_atencion": ahora(),
    }
    db["solicitudes_supresion"].update_one({"_id": solicitud_id}, {"$set": cambios})
    auditoria.registrar(db, "usuarios", usuario_id, "SUPRIMIR_DATOS", actor, {"solicitud_id": solicitud_id})
    return db["solicitudes_supresion"].find_one({"_id": solicitud_id})
