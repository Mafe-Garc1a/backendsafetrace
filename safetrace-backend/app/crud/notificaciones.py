"""Acceso a datos y reglas de K · Notificaciones y procesos (RF-69 a RF-71, RF-75).

Colecciones de las que es dueño: tareas, notificaciones.

Reglas clave:
- Solo avisos que piden acción o informan un hecho relevante (RNF-29).
- `datos` de una tarea guarda solo identificadores, nunca datos personales (RNF-20).
- Si una tarea falla y quedan intentos, vuelve a PENDIENTE más adelante (RNF-24).
- Cada notificación va por correo y al centro de notificaciones de la app (RF-75): `canales` y `leida_en`
  (Diseño DataBase v3, 10.4). Cada usuario ve y marca solo las suyas (RNF-10).
"""

from datetime import timedelta

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.fechas import ahora
from core.registro import request_id

TIPOS_NOTIFICACION = (
    "INMUEBLE_MARCADO_POR_SISMO",
    "CAMBIO_SOLICITUD",
    "SOLICITUD_ASIGNADA",  # aviso al perito de RF-49
    "CONSTANCIA_DISPONIBLE",
    "RECORDATORIO_SEMESTRAL",
)
CANALES = ["CORREO", "APP"]  # en el MVP, siempre los dos (RF-75)
SEGUNDOS_ENTRE_INTENTOS = 60


def encolar_tarea(db: Database, tipo: str, datos: dict, max_intentos: int = 3, session=None) -> ObjectId:
    """Crea una tarea PENDIENTE en la colección `tareas`. La usan todos."""
    momento = ahora()
    return (
        db["tareas"]
        .insert_one(
            {
                "tipo": tipo,
                "estado": "PENDIENTE",
                "datos": datos,
                "request_id": request_id.get(),
                "intentos": 0,
                "max_intentos": max_intentos,
                "disponible_desde": momento,
                "tomada_por": None,
                "tomada_en": None,
                "error": None,
                "creado_en": momento,
                "finalizada_en": None,
            },
            session=session,
        )
        .inserted_id
    )


def obtener_tarea(db: Database, tarea_id: ObjectId) -> dict | None:
    return db["tareas"].find_one({"_id": tarea_id})


def tomar_tarea(db: Database, trabajador: str) -> dict | None:
    """Toma UNA tarea pendiente de forma atómica: dos trabajadores nunca toman la misma."""
    momento = ahora()
    return db["tareas"].find_one_and_update(
        {"estado": "PENDIENTE", "disponible_desde": {"$lte": momento}},
        {"$set": {"estado": "PROCESANDO", "tomada_por": trabajador, "tomada_en": momento}, "$inc": {"intentos": 1}},
        sort=[("disponible_desde", 1), ("creado_en", 1)],
        return_document=ReturnDocument.AFTER,
    )


def tomar_tarea_atascada(db: Database, minutos: int) -> dict | None:
    """Toma UNA tarea abandonada en PROCESANDO; al renovar `tomada_en`, otro trabajador no la toma también."""
    momento = ahora()
    return db["tareas"].find_one_and_update(
        {"estado": "PROCESANDO", "tomada_en": {"$lte": momento - timedelta(minutes=minutos)}},
        {"$set": {"tomada_en": momento}},
        return_document=ReturnDocument.AFTER,
    )


def completar_tarea(db: Database, tarea_id: ObjectId) -> None:
    db["tareas"].update_one(
        {"_id": tarea_id}, {"$set": {"estado": "COMPLETADA", "error": None, "finalizada_en": ahora()}}
    )


def fallar_tarea(db: Database, tarea: dict, error: str) -> bool:
    """Devuelve True si la tarea quedó FALLIDA definitivamente; False si se reintentará."""
    momento = ahora()
    if tarea["intentos"] < tarea["max_intentos"]:
        espera = timedelta(seconds=SEGUNDOS_ENTRE_INTENTOS * tarea["intentos"])
        db["tareas"].update_one(
            {"_id": tarea["_id"]},
            {"$set": {"estado": "PENDIENTE", "error": error[:300], "disponible_desde": momento + espera}},
        )
        return False
    db["tareas"].update_one(
        {"_id": tarea["_id"]}, {"$set": {"estado": "FALLIDA", "error": error[:300], "finalizada_en": momento}}
    )
    return True


def posponer_tarea(db: Database, tarea: dict, segundos: float) -> None:
    """Devuelve la tarea a PENDIENTE sin gastar el intento: el problema es del proveedor, no de la tarea."""
    db["tareas"].update_one(
        {"_id": tarea["_id"]},
        {
            "$set": {"estado": "PENDIENTE", "disponible_desde": ahora() + timedelta(seconds=segundos)},
            "$inc": {"intentos": -1},
        },
    )


def notificar(db: Database, usuario_id: ObjectId, tipo: str, referencia: dict | None, session=None) -> ObjectId:
    """Registra la notificación y encola el correo (RF-37, RF-69, RF-70, RF-75). No guarda el texto del correo.

    Con `session` entra en la transacción de quien llama (asignación y firma de H).
    """
    if tipo not in TIPOS_NOTIFICACION:
        raise ValueError(f"Tipo de notificación desconocido: {tipo}")
    notificacion_id = (
        db["notificaciones"]
        .insert_one(
            {
                "usuario_id": usuario_id,
                "tipo": tipo,
                "referencia": referencia,
                "canales": list(CANALES),
                "estado": "PENDIENTE",
                "enviada_en": None,
                "leida_en": None,
                "schema_version": 3,
                "creado_en": ahora(),
            },
            session=session,
        )
        .inserted_id
    )
    encolar_tarea(db, "ENVIAR_CORREO", {"notificacion_id": notificacion_id}, session=session)
    return notificacion_id


def obtener_notificacion(db: Database, notificacion_id: ObjectId) -> dict | None:
    return db["notificaciones"].find_one({"_id": notificacion_id})


def marcar_notificacion(db: Database, notificacion_id: ObjectId, estado: str) -> None:
    cambios: dict = {"estado": estado}
    if estado == "ENVIADA":
        cambios["enviada_en"] = ahora()
    db["notificaciones"].update_one({"_id": notificacion_id}, {"$set": cambios})


def listar_notificaciones(db: Database, usuario_id: ObjectId, saltar: int, limite: int) -> tuple[list[dict], int]:
    filtros = {"usuario_id": usuario_id}
    total = db["notificaciones"].count_documents(filtros)
    datos = list(db["notificaciones"].find(filtros).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total


def contar_no_leidas(db: Database, usuario_id: ObjectId) -> int:
    """Contador del centro de notificaciones (RF-75)."""
    return db["notificaciones"].count_documents({"usuario_id": usuario_id, "leida_en": None})


def marcar_leida(db: Database, notificacion_id: ObjectId, usuario_id: ObjectId) -> dict | None:
    """Abrir una notificación llena `leida_en` una sola vez. None si no existe o es de otro usuario (RNF-10)."""
    db["notificaciones"].update_one(
        {"_id": notificacion_id, "usuario_id": usuario_id, "leida_en": None}, {"$set": {"leida_en": ahora()}}
    )
    return db["notificaciones"].find_one({"_id": notificacion_id, "usuario_id": usuario_id})


def marcar_todas_leidas(db: Database, usuario_id: ObjectId) -> int:
    resultado = db["notificaciones"].update_many(
        {"usuario_id": usuario_id, "leida_en": None}, {"$set": {"leida_en": ahora()}}
    )
    return resultado.modified_count
