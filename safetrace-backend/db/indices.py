"""Crea los índices del Diseño DataBase v3 (secciones 6 a 11). Ejecutar:  python -m db.indices

Se puede ejecutar varias veces: si un índice ya existe, MongoDB no lo duplica. Este script solo crea;
los índices que la v3 quita los borra la migración 0003 (`python -m db.migraciones.0003_indices`).

Los dos únicos parciales (sección 11.3) se crean aparte, cuando una prueba contra safetrace_test confirme
que funcionan (mongomock no reproduce bien los filtros parciales):  python -m db.indices --con-parciales
"""

import sys
from datetime import timedelta

from pymongo import ASCENDING as A
from pymongo import DESCENDING as D
from pymongo import GEOSPHERE

from core.database import obtener_db

INDICES = {
    # A · Cuentas
    "usuarios": [([("correo", A)], {"unique": True}), ([("rol", A), ("activo", A)], {})],
    "sesiones": [
        ([("expira_en", A)], {"expireAfterSeconds": 0}),
        ([("token_hash", A)], {"unique": True}),
        ([("usuario_id", A)], {}),
    ],
    "recuperaciones_contrasena": [
        ([("token_hash", A)], {"unique": True}),
        ([("expira_en", A)], {"expireAfterSeconds": 0}),
        ([("usuario_id", A), ("creado_en", D)], {}),
    ],
    "solicitudes_supresion": [([("usuario_id", A)], {}), ([("estado", A), ("fecha_solicitud", A)], {})],
    "permisos": [([("rol", A), ("modulo", A)], {"unique": True})],
    # B y C · Peritos e inmuebles
    "peritos": [
        ([("usuario_id", A)], {"unique": True}),
        ([("matricula_profesional", A)], {"unique": True}),
        ([("estado_credencial", A), ("ultima_asignacion_en", A)], {}),
    ],
    "inmuebles": [
        ([("ubicacion", GEOSPHERE)], {}),
        ([("propietario_id", A), ("creado_en", D)], {}),
        ([("estado.codigo", A)], {}),
        ([("revision_semestral.proxima", A)], {}),
    ],
    # D, E, F y G · Bitácora, revisiones, sismos y estados
    "eventos": [([("inmueble_id", A), ("fecha_evento", D)], {})],
    "evidencias": [
        ([("inmueble_id", A), ("zona_id", A), ("creado_en", D)], {}),
        ([("origen.tipo", A), ("origen.id", A)], {}),
        ([("inmueble_id", A), ("tipo_archivo", A), ("estado", A), ("creado_en", D)], {}),
    ],
    "revisiones": [([("inmueble_id", A), ("fecha", D)], {})],
    "sismos": [
        ([("fuentes.fuente", A), ("fuentes.id_externo", A)], {"unique": True}),
        ([("fecha_hora", D)], {}),
        ([("epicentro", GEOSPHERE)], {}),
    ],
    "historial_estados": [([("inmueble_id", A), ("fecha", D)], {})],
    # H e I · Solicitudes, inspecciones y enlace público
    "solicitudes_inspeccion": [
        ([("inmueble_id", A), ("creado_en", D)], {}),
        ([("estado", A), ("perito_id", A)], {}),
        ([("estado", A), ("creado_en", A)], {}),
        ([("perito_id", A), ("creado_en", D)], {}),
    ],
    "inspecciones": [
        ([("solicitud_id", A), ("version", A)], {"unique": True}),
        (
            [("constancia.codigo", A)],
            {"unique": True, "partialFilterExpression": {"constancia.codigo": {"$type": "string"}}},
        ),
        ([("inmueble_id", A), ("version", D)], {}),
        ([("constancia.vigente_hasta", A)], {}),
        ([("version_anterior_id", A)], {}),
    ],
    "enlaces_publicos": [([("codigo", A)], {"unique": True}), ([("inmueble_id", A), ("activo", A)], {})],
    # J y K · IA, índice, tareas, notificaciones y auditoría
    "analisis_ia": [
        ([("clave_par", A)], {"unique": True}),
        ([("inmueble_id", A), ("creado_en", D)], {}),
        ([("estado", A)], {}),
        ([("evidencia_anterior_id", A)], {}),
        ([("evidencia_nueva_id", A)], {}),
    ],
    "indices_priorizacion": [
        ([("inmueble_id", A), ("sismo_id", A)], {"unique": True}),
        ([("sismo_id", A), ("valor", D)], {}),
        ([("inmueble_id", A), ("calculado_en", D)], {}),
    ],
    "tareas": [
        ([("estado", A), ("disponible_desde", A), ("creado_en", A)], {}),
        ([("estado", A), ("tomada_en", A)], {}),
        (
            [("finalizada_en", A)],
            {
                "expireAfterSeconds": int(timedelta(days=30).total_seconds()),
                "partialFilterExpression": {"estado": "COMPLETADA"},
            },
        ),
    ],
    "notificaciones": [([("usuario_id", A), ("creado_en", D)], {}), ([("usuario_id", A), ("leida_en", A)], {})],
    "auditoria": [
        ([("coleccion", A), ("documento_id", A), ("fecha", D)], {}),
        ([("actor.id", A), ("fecha", D)], {}),
        ([("fecha", D)], {}),
    ],
}

# Segunda barrera ante dos peticiones simultáneas (sección 11.3). El código ya impide estos duplicados.
INDICES_PARCIALES = {
    "eventos": [
        (
            [("inmueble_id", A), ("sismo_id", A)],
            {
                "unique": True,
                "name": "un_sismo_por_inmueble",
                "partialFilterExpression": {"tipo": "EVENTO_EXTERNO"},
            },
        )
    ],
    "solicitudes_inspeccion": [
        (
            [("inmueble_id", A)],
            {
                "unique": True,
                "name": "una_solicitud_abierta_por_inmueble",
                "partialFilterExpression": {"estado": {"$in": ["PENDIENTE_ASIGNACION", "ASIGNADA"]}},
            },
        )
    ],
}


def crear(db=None, con_parciales: bool = False, silencioso: bool = False):
    db = db if db is not None else obtener_db()
    grupos = [INDICES, INDICES_PARCIALES] if con_parciales else [INDICES]
    for grupo in grupos:
        for coleccion, indices in grupo.items():
            for claves, opciones in indices:
                db[coleccion].create_index(claves, **opciones)
            if not silencioso:
                print(f"ok  {coleccion}: {len(indices)} índices")


if __name__ == "__main__":
    crear(con_parciales="--con-parciales" in sys.argv)
