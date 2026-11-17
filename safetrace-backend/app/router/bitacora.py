"""Rutas de D · Bitácora y evidencias (RF-22 a RF-27)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database

from app.crud import bitacora as crud_bitacora
from app.crud import peritos as crud_peritos
from app.router.comunes import url_archivo, validar_zona
from app.router.dependencies import get_current_user, obtener_inmueble_autorizado, requiere_permiso
from app.schemas.bitacora import (
    EXTENSIONES,
    AutorizacionSubidaCreate,
    AutorizacionSubidaOut,
    EventoCreate,
    EventoOut,
    EvidenciaCreate,
    EvidenciaOut,
    InvalidacionCreate,
    InvalidacionEventoCreate,
    LineaCronologicaPage,
    UrlArchivoOut,
)
from core import almacenamiento
from core.config import settings
from core.database import a_object_id, get_db, serializar
from core.fechas import ahora, en_utc
from core.paginacion import Pagina

router = APIRouter()
modulo = "bitacora"
modulo_archivos = "archivos"
modulo_perito = "perfil_perito"


@router.post(
    "/inmuebles/{inmueble_id}/eventos",
    response_model=EventoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un evento",
    description="RF-22, RF-23",
)
def registrar_evento(
    inmueble_id: str,
    evento: EventoCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    if en_utc(evento.fecha_evento) > ahora() + timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="La fecha del evento no puede estar en el futuro")
    validar_zona(db, evento.zona_id)
    return serializar(crud_bitacora.registrar_evento(db, inmueble["_id"], evento, usuario))


@router.get(
    "/inmuebles/{inmueble_id}/linea-cronologica",
    response_model=LineaCronologicaPage,
    summary="Eventos y evidencias, de a 50",
    description="RF-26, RNF-30",
)
def linea_cronologica(
    inmueble_id: str,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    datos, total = crud_bitacora.linea_cronologica(db, inmueble["_id"], pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


def _validar_tamano(tamano_bytes: int) -> None:
    maximo_mb = settings.archivos_tamano_maximo_mb
    if tamano_bytes > maximo_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera el máximo de {maximo_mb} MB")


def _autorizar(ruta: str, tipo_contenido: str, tamano_bytes: int) -> dict:
    try:
        return {"ruta": ruta, **almacenamiento.autorizacion_subida(ruta, tipo_contenido, tamano_bytes)}
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from None


@router.post(
    "/archivos/autorizacion",
    response_model=AutorizacionSubidaOut,
    summary="Autorización temporal para subir directo al proveedor",
    description="RF-24, RF-25. El navegador sube con PUT; luego registra la evidencia con `ruta` y la huella.",
)
def autorizar_subida(
    solicitud: AutorizacionSubidaCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo_archivos, "insertar")),
):
    inmueble = obtener_inmueble_autorizado(db, solicitud.inmueble_id, usuario)
    _validar_tamano(solicitud.tamano_bytes)
    momento = ahora()
    extension = EXTENSIONES[solicitud.tipo_contenido]
    ruta = f"{almacenamiento.prefijo_inmueble(inmueble['_id'])}{momento:%Y/%m}/{momento:%d%H%M%S%f}.{extension}"
    return _autorizar(ruta, solicitud.tipo_contenido, solicitud.tamano_bytes)


@router.post(
    "/peritos/archivos/autorizacion",
    response_model=AutorizacionSubidaOut,
    summary="Autorización para que el perito suba sus documentos profesionales (PDF)",
    description="RF-14",
)
def autorizar_subida_perito(
    nombre_archivo: str = Query(min_length=1, max_length=120),  # solo informativo
    tamano_bytes: int = Query(gt=0),
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo_perito, "insertar")),
):
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    if perito is None:
        raise HTTPException(status_code=404, detail="Primero registre su perfil profesional")
    _validar_tamano(tamano_bytes)
    momento = ahora()
    ruta = f"{almacenamiento.prefijo_perito(perito['_id'])}{momento:%Y%m%d%H%M%S%f}.pdf"
    return _autorizar(ruta, "application/pdf", tamano_bytes)


@router.get(
    "/evidencias/{evidencia_id}/archivo",
    response_model=UrlArchivoOut,
    summary="URL temporal para ver la foto o el documento de una evidencia",
    description="RF-26. Quien puede ver el inmueble puede ver sus evidencias, también las invalidadas.",
)
def ver_archivo_evidencia(
    evidencia_id: str,
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    evidencia = crud_bitacora.obtener_evidencia(db, a_object_id(evidencia_id))
    if evidencia is None:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    obtener_inmueble_autorizado(db, evidencia["inmueble_id"], usuario)
    return url_archivo(evidencia["archivo"]["ruta"], almacenamiento.prefijo_inmueble(evidencia["inmueble_id"]))


@router.post(
    "/inmuebles/{inmueble_id}/evidencias",
    response_model=EvidenciaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar la referencia de un archivo ya subido (adjunto a un evento)",
    description="RF-24, RF-25",
)
def registrar_evidencia(
    inmueble_id: str,
    evidencia: EvidenciaCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    evento = crud_bitacora.obtener_evento(db, a_object_id(evidencia.evento_id))
    if evento is None or evento["inmueble_id"] != inmueble["_id"]:
        raise HTTPException(status_code=404, detail="Evento no encontrado en este inmueble")
    validar_zona(db, evidencia.zona_id)
    creada = crud_bitacora.registrar_evidencia(db, inmueble["_id"], "EVENTO", evento["_id"], evidencia, usuario)
    return serializar(creada)


@router.patch(
    "/eventos/{evento_id}/invalidacion",
    response_model=EventoOut,
    summary="Marcar un evento inválido o reemplazado (no se edita ni se borra)",
    description="RF-22, RNF-16, RNF-21. Diseño DataBase v3, 8.1.",
)
def invalidar_evento(
    evento_id: str,
    cambio: InvalidacionEventoCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    evento = crud_bitacora.obtener_evento(db, a_object_id(evento_id))
    if evento is None:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    obtener_inmueble_autorizado(db, evento["inmueble_id"], usuario, solo_propietario=True)
    if evento["origen"] == "SISTEMA":
        raise HTTPException(status_code=403, detail="Los eventos del sistema (sismos) no se invalidan")

    reemplazo_id = None
    if cambio.reemplazado_por:
        reemplazo = crud_bitacora.obtener_evento(db, a_object_id(cambio.reemplazado_por))
        if (
            reemplazo is None
            or reemplazo["_id"] == evento["_id"]
            or reemplazo["inmueble_id"] != evento["inmueble_id"]
            or reemplazo.get("estado", "VIGENTE") != "VIGENTE"
        ):
            raise HTTPException(status_code=400, detail="El evento de reemplazo no es válido")
        reemplazo_id = reemplazo["_id"]

    actualizado = crud_bitacora.invalidar_evento(db, evento, cambio.estado, cambio.motivo, reemplazo_id, usuario)
    if actualizado is None:
        raise HTTPException(status_code=409, detail="El evento ya no está vigente")
    return serializar(actualizado)


@router.patch(
    "/evidencias/{evidencia_id}/invalidacion",
    response_model=EvidenciaOut,
    summary="Marcar evidencia inválida o reemplazada",
    description="RF-27",
)
def invalidar_evidencia(
    evidencia_id: str,
    cambio: InvalidacionCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    evidencia = crud_bitacora.obtener_evidencia(db, a_object_id(evidencia_id))
    if evidencia is None:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    obtener_inmueble_autorizado(db, evidencia["inmueble_id"], usuario, solo_propietario=True)
    if evidencia["origen"]["tipo"] == "INSPECCION":
        raise HTTPException(status_code=403, detail="Las evidencias de una inspección solo las corrige el perito")

    reemplazo_id = None
    if cambio.reemplazada_por:
        reemplazo = crud_bitacora.obtener_evidencia(db, a_object_id(cambio.reemplazada_por))
        if (
            reemplazo is None
            or reemplazo["_id"] == evidencia["_id"]
            or reemplazo["inmueble_id"] != evidencia["inmueble_id"]
            or reemplazo["estado"] != "VIGENTE"
        ):
            raise HTTPException(status_code=400, detail="La evidencia de reemplazo no es válida")
        reemplazo_id = reemplazo["_id"]

    actualizada = crud_bitacora.invalidar_evidencia(db, evidencia, cambio.estado, cambio.motivo, reemplazo_id, usuario)
    if actualizada is None:
        raise HTTPException(status_code=409, detail="La evidencia ya no está vigente")
    return serializar(actualizada)
