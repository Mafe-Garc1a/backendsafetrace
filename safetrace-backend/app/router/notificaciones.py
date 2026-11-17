"""Rutas de K · Notificaciones y procesos (RF-69 a RF-71, RF-75)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import ia_indice as crud_ia
from app.crud import notificaciones as crud_notificaciones
from app.router.dependencies import get_current_user, obtener_inmueble_autorizado, puede_supervisar
from app.schemas.notificaciones import ContadorNoLeidas, NotificacionOut, NotificacionPage, TareaOut
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()


@router.get(
    "/tareas/{tarea_id}",
    response_model=TareaOut,
    summary="Estado de una operación en segundo plano",
    description="RF-71",
)
def consultar_tarea(tarea_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    """Solo quien puede ver el recurso de la tarea (RNF-10): el inmueble del análisis de IA, o el administrador."""
    tarea = crud_notificaciones.obtener_tarea(db, a_object_id(tarea_id))
    if tarea is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    analisis_id = tarea["datos"].get("analisis_id")
    analisis = crud_ia.obtener_analisis(db, analisis_id) if analisis_id else None
    if analisis is not None:
        obtener_inmueble_autorizado(db, analisis["inmueble_id"], usuario)
    elif not puede_supervisar(db, usuario):
        raise HTTPException(status_code=403, detail="Sin permiso sobre esta tarea")
    return serializar(tarea)


@router.get(
    "/notificaciones",
    response_model=NotificacionPage,
    summary="Avisos enviados al usuario de la sesión",
    description="RF-37, RF-69, RF-70",
)
def mis_notificaciones(
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    datos, total = crud_notificaciones.listar_notificaciones(db, usuario["_id"], pagina.saltar, pagina.tamano)
    respuesta = pagina.respuesta(serializar(datos), total)
    respuesta["no_leidas"] = crud_notificaciones.contar_no_leidas(db, usuario["_id"])
    return respuesta


@router.get(
    "/notificaciones/no-leidas",
    response_model=ContadorNoLeidas,
    summary="Cuántas notificaciones no ha leído el usuario",
    description="RF-75",
)
def contar_no_leidas(db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    return {"no_leidas": crud_notificaciones.contar_no_leidas(db, usuario["_id"])}


@router.patch(
    "/notificaciones/{notificacion_id}/lectura",
    response_model=NotificacionOut,
    summary="Marcar una notificación como leída",
    description="RF-75",
)
def marcar_leida(notificacion_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    notificacion = crud_notificaciones.marcar_leida(db, a_object_id(notificacion_id), usuario["_id"])
    if notificacion is None:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    return serializar(notificacion)


@router.post(
    "/notificaciones/lectura",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marcar todas las notificaciones como leídas",
    description="RF-75",
)
def marcar_todas_leidas(db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    crud_notificaciones.marcar_todas_leidas(db, usuario["_id"])
