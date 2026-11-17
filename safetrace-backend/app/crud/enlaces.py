"""Acceso a datos y reglas de I · Enlace público (RF-59 a RF-61).

Colecciones de las que es dueño: enlaces_publicos.
No ofrece operaciones a otros módulos.

Reglas clave:
- Nunca devuelve el estado ni datos personales (RNF-18, RNF-19), ni las observaciones de una inspección (RNF-38).
- Código aleatorio y largo. Revocar no borra: deja activo false, revocado_en y revocado_por (RF-61, RNF-21).
- De las inspecciones solo muestra la versión activa de cada solicitud; el perito sale de la copia guardada
  en la firma (Diseño DataBase v3, 9.2 y 9.3).
"""

import secrets

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from app.crud import auditoria
from app.crud import bitacora as crud_bitacora
from app.crud import inmuebles as crud_inmuebles
from app.crud import inspecciones as crud_inspecciones
from core import almacenamiento
from core.fechas import ahora

AVISO_PUBLICO = (
    "Información compartida por el propietario. SafeTrace no certifica que el inmueble sea seguro "
    "ni habitable; las inspecciones firmadas son responsabilidad del perito que las firma."
)


def crear_enlace(db: Database, inmueble_id: ObjectId, campos: list[str], usuario: dict) -> dict:
    documento = {
        "inmueble_id": inmueble_id,
        "codigo": secrets.token_urlsafe(15),  # 20 caracteres aleatorios
        "campos_compartidos": list(dict.fromkeys(campos)),
        "activo": True,
        "creado_por": usuario["_id"],
        "creado_en": ahora(),
        "revocado_en": None,
        "revocado_por": None,
    }
    documento["_id"] = db["enlaces_publicos"].insert_one(documento).inserted_id
    auditoria.registrar(
        db,
        "enlaces_publicos",
        documento["_id"],
        "CREAR_ENLACE",
        auditoria.actor_usuario(usuario),
        {"campos_compartidos": documento["campos_compartidos"]},
    )
    return documento


def listar_enlaces(db: Database, inmueble_id: ObjectId) -> list[dict]:
    return list(db["enlaces_publicos"].find({"inmueble_id": inmueble_id}).sort("creado_en", -1))


def obtener_enlace(db: Database, enlace_id: ObjectId) -> dict | None:
    return db["enlaces_publicos"].find_one({"_id": enlace_id})


def revocar_enlace(db: Database, enlace: dict, usuario: dict) -> dict | None:
    revocado = db["enlaces_publicos"].find_one_and_update(
        {"_id": enlace["_id"], "activo": True},
        {"$set": {"activo": False, "revocado_en": ahora(), "revocado_por": usuario["_id"]}},
        return_document=ReturnDocument.AFTER,
    )
    if revocado:
        auditoria.registrar(db, "enlaces_publicos", enlace["_id"], "REVOCAR_ENLACE", auditoria.actor_usuario(usuario))
    return revocado


def vista_publica(db: Database, codigo: str) -> dict | None:
    """Arma la vista de solo lectura con los campos autorizados, sin estado ni datos personales."""
    enlace = db["enlaces_publicos"].find_one({"codigo": codigo, "activo": True})
    if enlace is None:
        return None
    inmueble_id = enlace["inmueble_id"]
    campos = enlace["campos_compartidos"]
    vista: dict = {
        "inmueble": crud_inmuebles.datos_publicos(db, inmueble_id),
        "campos_compartidos": campos,
        "aviso": AVISO_PUBLICO,
    }
    if "LINEA_CRONOLOGICA" in campos:
        eventos, _ = crud_bitacora.linea_cronologica(db, inmueble_id, 0, 50)
        vista["linea_cronologica"] = [
            {
                "tipo": e["tipo"],
                "fecha_evento": e["fecha_evento"],
                "descripcion": e["descripcion"],
                "zona_id": e["zona_id"],
            }
            for e in eventos
        ]
    if "FOTOS" in campos:
        vista["fotos"] = [
            {"zona_id": f["zona_id"], "fecha": f["creado_en"], **_url_publica(f["archivo"]["ruta"])}
            for f in crud_bitacora.fotos_vigentes(db, inmueble_id)
        ]
    if "INSPECCIONES_FIRMADAS" in campos:
        vista["inspecciones_firmadas"] = [
            _inspeccion_publica(i) for i in crud_inspecciones.constancias_activas(db, inmueble_id)
        ]
    return vista


def _url_publica(ruta: str) -> dict:
    """URL temporal de la foto, sin exponer la ruta interna. Sin proveedor, la vista sigue sin la imagen (RNF-24)."""
    try:
        return almacenamiento.url_lectura(ruta)
    except NotImplementedError:
        return {"url": None, "expira_en": None}


def _inspeccion_publica(inspeccion: dict) -> dict:
    """Hallazgos y resultado, sí; observaciones, nunca (RNF-38)."""
    constancia = inspeccion["constancia"]
    perito = inspeccion["firma"]["perito"]
    return {
        "fecha_inspeccion": inspeccion["fecha_inspeccion"],
        "hallazgos": inspeccion["hallazgos"],
        "resultado": inspeccion["resultado"],
        "constancia": {
            "codigo": constancia["codigo"],
            "estado": inspeccion["estado_constancia"],
            "emitida_en": constancia["emitida_en"],
            "vigente_hasta": constancia["vigente_hasta"],
        },
        "perito": {
            "nombre_completo": perito["nombre_completo"],
            "profesion": perito["profesion"],
            "matricula_profesional": perito["matricula_profesional"],
        },
        "aviso_legal": inspeccion["aviso_legal"],
    }
