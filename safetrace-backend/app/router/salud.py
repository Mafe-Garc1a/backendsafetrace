"""Rutas del sistema: raíz y estado de la API (Infraestructura, RNF-05).

Estructura del backend v2: /salud informará también el estado de MongoDB y Redis cuando entre el cliente de Redis
(fase 2 de la Integración Redis v2, a cargo de Nicolás).
"""

from fastapi import APIRouter

from core.config import settings

router = APIRouter()


@router.get("/")
def read_root():
    return {"message": "ok", "proyecto": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION}


@router.get("/salud")
def salud():
    return {"estado": "ok"}
