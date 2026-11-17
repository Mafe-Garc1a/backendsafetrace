"""Ayudas de rutas que usan varios módulos (sin dueño de módulo; las mantiene quien las cambie con revisión).

Antes vivían en `router/bitacora.py` y B, E y H dependían de las rutas de D (hallazgo B-1 de la revisión
de estructura). Aquí no hay reglas de negocio: solo traducen datos de entrada a errores HTTP.
"""

from fastapi import HTTPException
from pymongo.database import Database

from app.crud import inmuebles as crud_inmuebles
from core import almacenamiento


def validar_zona(db: Database, zona_id: str | None) -> None:
    """La zona existe en el catálogo y está activa (RF-23). La usan D, E y H."""
    if zona_id is not None and not crud_inmuebles.zona_activa(db, zona_id):
        raise HTTPException(status_code=400, detail=f"Zona no válida: {zona_id}")


def url_archivo(ruta: str, prefijo: str) -> dict:
    """URL temporal de lectura de un archivo ya registrado. La usan D (evidencias) y B (documentos del perito)."""
    if not almacenamiento.ruta_valida(ruta, prefijo):
        raise HTTPException(status_code=404, detail="Archivo no disponible")
    try:
        return almacenamiento.url_lectura(ruta)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from None
