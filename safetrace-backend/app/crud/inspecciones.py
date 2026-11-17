"""Acceso a datos de H · Inspecciones y constancias (RF-48 a RF-58, RF-72). Dueño: Juan Miguel.

Colecciones de las que es dueño: solicitudes_inspeccion, inspecciones (Diseño DataBase v3, 9.1 y 9.2).
Solo este archivo las escribe; las reglas del módulo están en `app/servicios/inspecciones.py`.

Reglas que cuida la base:
- Una solicitud solo avanza: PENDIENTE_ASIGNACION → ASIGNADA → ATENDIDA (RF-72). Cada paso es una
  escritura con condición sobre el estado anterior, así que dos procesos no la mueven dos veces.
- Una inspección es borrador mientras `firma` es null. La firma se guarda con la condición `firma: null`
  y desde entonces el documento no se vuelve a escribir (RNF-13).
- No se guardan `constancia.estado` ni `es_version_activa`: se calculan al leer.
"""

import hashlib
import json
import secrets
from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.fechas import ahora, en_utc

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para evitar confusiones
LONGITUD_CODIGO = 16

ESTADO_PENDIENTE = "PENDIENTE_ASIGNACION"
ESTADO_ASIGNADA = "ASIGNADA"
ESTADO_ATENDIDA = "ATENDIDA"
ABIERTAS = (ESTADO_PENDIENTE, ESTADO_ASIGNADA)


# --- Código y huella (RF-52, RF-54, RF-58) -------------------------------------------


def generar_codigo(longitud: int = LONGITUD_CODIGO) -> str:
    """Código aleatorio con generador criptográfico; nunca consecutivo (RF-58)."""
    return "".join(secrets.choice(ALFABETO) for _ in range(longitud))


def _normalizar(valor):
    """Fechas en UTC con milisegundos e ids como texto: igual antes y después de guardar en MongoDB."""
    if isinstance(valor, datetime):
        return en_utc(valor).isoformat(timespec="milliseconds")
    return str(valor)


def huella_contenido(contenido: dict) -> str:
    """SHA-256 del contenido firmado, en JSON canónico (claves ordenadas)."""
    canonico = json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=_normalizar, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def contenido_firmable(inspeccion: dict, firma: dict, constancia: dict) -> dict:
    """Todo lo que cubre la firma, incluida la copia de los datos del perito (Diseño DataBase v3, 9.2)."""
    return {
        "id": inspeccion["_id"],
        "solicitud_id": inspeccion["solicitud_id"],
        "inmueble_id": inspeccion["inmueble_id"],
        "perito_id": inspeccion["perito_id"],
        "version": inspeccion["version"],
        "version_anterior_id": inspeccion.get("version_anterior_id"),
        "fecha_inspeccion": inspeccion["fecha_inspeccion"],
        "motivo": inspeccion["motivo"],
        "observaciones": inspeccion["observaciones"],
        "hallazgos": inspeccion["hallazgos"],
        "resultado": inspeccion["resultado"],
        "evidencias_ids": inspeccion.get("evidencias_ids", []),
        "aviso_legal": inspeccion["aviso_legal"],
        "firma_fecha": firma["fecha"],
        "firma_metodo": firma["metodo"],
        "firma_perito": firma["perito"],
        "constancia_codigo": constancia["codigo"],
        "constancia_emitida_en": constancia["emitida_en"],
        "constancia_vigencia_meses": constancia["vigencia_meses"],
        "constancia_vigente_hasta": constancia["vigente_hasta"],
    }


def es_integra(inspeccion: dict) -> bool:
    """Recalcula la huella y la compara con la guardada al firmar (RF-58)."""
    firma = inspeccion.get("firma")
    constancia = inspeccion.get("constancia")
    if not firma or not constancia:
        return False
    return huella_contenido(contenido_firmable(inspeccion, firma, constancia)) == firma["huella_sha256"]


# --- Solicitudes (9.1) ----------------------------------------------------------------


def insertar_solicitud(db: Database, documento: dict, session=None) -> dict:
    documento["_id"] = db["solicitudes_inspeccion"].insert_one(documento, session=session).inserted_id
    return documento


def obtener_solicitud(db: Database, solicitud_id: ObjectId, session=None) -> dict | None:
    return db["solicitudes_inspeccion"].find_one({"_id": solicitud_id}, session=session)


def hay_solicitud_abierta(db: Database, inmueble_id: ObjectId) -> bool:
    """Un inmueble tiene como máximo una solicitud abierta (BD-05)."""
    filtro = {"inmueble_id": inmueble_id, "estado": {"$in": list(ABIERTAS)}}
    return db["solicitudes_inspeccion"].count_documents(filtro, limit=1) > 0


def listar_solicitudes(db: Database, filtros: dict, saltar: int, limite: int) -> tuple[list[dict], int]:
    total = db["solicitudes_inspeccion"].count_documents(filtros)
    datos = list(db["solicitudes_inspeccion"].find(filtros).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total


def pendientes_mas_antiguas(db: Database, limite: int = 100) -> list[dict]:
    """Solicitudes sin perito, de la más antigua a la más nueva (RF-49)."""
    return list(db["solicitudes_inspeccion"].find({"estado": ESTADO_PENDIENTE}).sort("creado_en", 1).limit(limite))


def asignadas_por_perito(db: Database, peritos_ids: list[ObjectId]) -> dict[ObjectId, int]:
    """Cuántas solicitudes ASIGNADA tiene cada perito. Las ATENDIDA no cuentan (RF-49)."""
    conteo = db["solicitudes_inspeccion"].aggregate(
        [
            {"$match": {"estado": ESTADO_ASIGNADA, "perito_id": {"$in": peritos_ids}}},
            {"$group": {"_id": "$perito_id", "n": {"$sum": 1}}},
        ]
    )
    return {fila["_id"]: fila["n"] for fila in conteo}


def marcar_asignada(
    db: Database, solicitud_id: ObjectId, perito_id: ObjectId, activas: int, momento: datetime, session=None
) -> dict | None:
    """PENDIENTE_ASIGNACION → ASIGNADA. None si ya no estaba pendiente (otra asignación ganó)."""
    return db["solicitudes_inspeccion"].find_one_and_update(
        {"_id": solicitud_id, "estado": ESTADO_PENDIENTE},
        {
            "$set": {
                "estado": ESTADO_ASIGNADA,
                "perito_id": perito_id,
                "asignacion": {"metodo": "AUTOMATICA", "fecha": momento, "solicitudes_activas_del_perito": activas},
            },
            "$push": {"cambios_estado": {"estado": ESTADO_ASIGNADA, "fecha": momento}},
        },
        return_document=ReturnDocument.AFTER,
        session=session,
    )


def marcar_atendida(db: Database, solicitud_id: ObjectId, momento: datetime, session=None) -> bool:
    """ASIGNADA → ATENDIDA cuando el perito firma (RF-72). False si ya estaba atendida."""
    resultado = db["solicitudes_inspeccion"].update_one(
        {"_id": solicitud_id, "estado": ESTADO_ASIGNADA},
        {
            "$set": {"estado": ESTADO_ATENDIDA},
            "$push": {"cambios_estado": {"estado": ESTADO_ATENDIDA, "fecha": momento}},
        },
        session=session,
    )
    return resultado.modified_count == 1


def perito_asignado_a_inmueble(db: Database, inmueble_id: ObjectId, usuario_id: ObjectId) -> bool:
    """True si el usuario es el perito de alguna solicitud ASIGNADA o ATENDIDA del inmueble (RF-47, RNF-10).

    Lo usa `obtener_inmueble_autorizado`. Lee `peritos` sin pasar por B para no crear un ciclo de imports
    entre las dependencias y los servicios.
    """
    perito = db["peritos"].find_one({"usuario_id": usuario_id}, {"_id": 1})
    if perito is None:
        return False
    filtro = {
        "inmueble_id": inmueble_id,
        "perito_id": perito["_id"],
        "estado": {"$in": [ESTADO_ASIGNADA, ESTADO_ATENDIDA]},
    }
    return db["solicitudes_inspeccion"].count_documents(filtro, limit=1) > 0


# --- Inspecciones (9.2) -----------------------------------------------------------------


def insertar_inspeccion(db: Database, documento: dict) -> dict:
    """Versión nueva en borrador. El índice único (solicitud_id, version) impide dos versiones iguales."""
    documento["_id"] = db["inspecciones"].insert_one(documento).inserted_id
    return documento


def obtener_inspeccion(db: Database, inspeccion_id: ObjectId) -> dict | None:
    return db["inspecciones"].find_one({"_id": inspeccion_id})


def versiones_de_solicitud(db: Database, solicitud_id: ObjectId) -> list[dict]:
    """Todas las versiones de una solicitud, de la más nueva a la más antigua."""
    return list(db["inspecciones"].find({"solicitud_id": solicitud_id}).sort("version", -1))


def listar_de_inmueble(db: Database, inmueble_id: ObjectId) -> list[dict]:
    return list(db["inspecciones"].find({"inmueble_id": inmueble_id}).sort([("version", -1), ("creado_en", -1)]))


def actualizar_borrador(db: Database, inspeccion_id: ObjectId, datos: dict) -> dict | None:
    """Solo mientras no está firmada. None si ya se firmó (RNF-13)."""
    return db["inspecciones"].find_one_and_update(
        {"_id": inspeccion_id, "firma": None}, {"$set": datos}, return_document=ReturnDocument.AFTER
    )


def agregar_evidencias(db: Database, inspeccion_id: ObjectId, evidencias_ids: list[ObjectId]) -> None:
    """Solo en borrador: las evidencias de una inspección firmada no cambian (RNF-13)."""
    db["inspecciones"].update_one(
        {"_id": inspeccion_id, "firma": None}, {"$push": {"evidencias_ids": {"$each": evidencias_ids}}}
    )


def guardar_firma(db: Database, inspeccion_id: ObjectId, firma: dict, constancia: dict, session=None) -> dict | None:
    """Firma y constancia en una sola escritura con condición `firma: null`. None si ya estaba firmada."""
    return db["inspecciones"].find_one_and_update(
        {"_id": inspeccion_id, "firma": None},
        {"$set": {"firma": firma, "constancia": constancia}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )


def codigo_en_uso(db: Database, codigo: str) -> bool:
    return db["inspecciones"].count_documents({"constancia.codigo": codigo}, limit=1) > 0


def obtener_por_codigo(db: Database, codigo: str) -> dict | None:
    return db["inspecciones"].find_one({"constancia.codigo": codigo, "firma": {"$ne": None}})


def firmadas_vencidas(db: Database, momento: datetime) -> list[dict]:
    """Inspecciones firmadas cuya constancia ya venció (RF-44, RF-56). La tarea diaria solo las lee."""
    return list(
        db["inspecciones"].find(
            {"firma": {"$ne": None}, "constancia.vigente_hasta": {"$lt": momento}},
            {"solicitud_id": 1, "inmueble_id": 1, "version": 1, "constancia": 1},
        )
    )


def firmadas_de_inmueble(db: Database, inmueble_id: ObjectId) -> list[dict]:
    """Versiones firmadas del inmueble, la más nueva primero. Las usan la vista pública (I) y el cálculo de activas."""
    return list(db["inspecciones"].find({"inmueble_id": inmueble_id, "firma": {"$ne": None}}).sort("firma.fecha", -1))


# --- Valores que se calculan al leer (9.2): no se guardan ------------------------------------


def estado_constancia(inspeccion: dict, momento: datetime | None = None) -> str | None:
    """VIGENTE o VENCIDA según `vigente_hasta` (RF-56). None en borrador."""
    constancia = inspeccion.get("constancia")
    if not constancia:
        return None
    return "VIGENTE" if (momento or ahora()) < en_utc(constancia["vigente_hasta"]) else "VENCIDA"


def version_activa(versiones: list[dict]) -> dict | None:
    """La versión firmada de número mayor (9.2)."""
    firmadas = [v for v in versiones if v.get("firma") is not None]
    return max(firmadas, key=lambda v: v["version"]) if firmadas else None


def reemplazo(versiones: list[dict], inspeccion: dict) -> int | None:
    """Número de la versión firmada posterior que reemplaza a esta, si existe."""
    posteriores = [
        v["version"] for v in versiones if v.get("firma") is not None and v["version"] > inspeccion["version"]
    ]
    return max(posteriores) if posteriores else None


def constancias_activas(db: Database, inmueble_id: ObjectId) -> list[dict]:
    """Versión activa (firmada y no reemplazada) de cada solicitud del inmueble, con su estado. La usa I."""
    activas: dict = {}
    for inspeccion in firmadas_de_inmueble(db, inmueble_id):
        actual = activas.get(inspeccion["solicitud_id"])
        if actual is None or inspeccion["version"] > actual["version"]:
            activas[inspeccion["solicitud_id"]] = inspeccion
    return [{**i, "estado_constancia": estado_constancia(i)} for i in activas.values()]
