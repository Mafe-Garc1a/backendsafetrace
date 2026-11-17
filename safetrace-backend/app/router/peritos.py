"""Rutas de B · Peritos (RF-13 a RF-16, RNF-15)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import peritos as crud_peritos
from app.crud.auditoria import actor_usuario
from app.router.comunes import url_archivo
from app.router.dependencies import requiere_permiso, requiere_servicio_n8n
from app.schemas.bitacora import UrlArchivoOut
from app.schemas.peritos import (
    DocumentosCreate,
    EstadoCredencial,
    InconsistenciaCreate,
    PeritoCreate,
    PeritoOut,
    ValidacionCreate,
)
from app.servicios import inspecciones as servicio_inspecciones
from core import almacenamiento
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()
modulo = "perfil_perito"
modulo_validacion = "validacion_peritos"


def _mi_perfil(db: Database, usuario: dict) -> dict:
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    if perito is None:
        raise HTTPException(status_code=404, detail="Primero registre su perfil profesional")
    return perito


@router.post(
    "/peritos/perfil",
    response_model=PeritoOut,
    status_code=status.HTTP_201_CREATED,
    summary="El perito registra su perfil profesional",
    description="RF-13",
)
def registrar_perfil(
    perfil: PeritoCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    perito = crud_peritos.crear_perfil(db, usuario["_id"], perfil)
    return serializar(perito)


@router.post(
    "/peritos/documentos",
    response_model=PeritoOut,
    summary="Registrar referencias de documentos ya subidos al proveedor",
    description="RF-14",
)
def registrar_documentos(
    datos: DocumentosCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    perito = _mi_perfil(db, usuario)
    return serializar(crud_peritos.agregar_documentos(db, perito, datos.documentos))


@router.get(
    "/peritos/mi-estado",
    response_model=PeritoOut,
    summary="El perito consulta el estado de sus credenciales",
    description="RF-13",
)
def consultar_mi_estado(
    db: Database = Depends(get_db), usuario: dict = Depends(requiere_permiso(modulo, "seleccionar"))
):
    return serializar(_mi_perfil(db, usuario))


def _url_documento(perito: dict, documento_id: str) -> dict:
    documento = next((d for d in perito.get("documentos", []) if d["documento_id"] == documento_id), None)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return url_archivo(documento["archivo"]["ruta"], almacenamiento.prefijo_perito(perito["_id"]))


@router.get(
    "/peritos/documentos/{documento_id}/archivo",
    response_model=UrlArchivoOut,
    summary="El perito obtiene una URL temporal para ver uno de sus documentos",
    description="RF-14",
)
def ver_mi_documento(
    documento_id: str,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    return _url_documento(_mi_perfil(db, usuario), documento_id)


@router.get(
    "/admin/peritos/{perito_id}/documentos/{documento_id}/archivo",
    response_model=UrlArchivoOut,
    summary="URL temporal para revisar un documento del perito antes de validarlo",
    description="RF-15",
)
def ver_documento_perito(
    perito_id: str,
    documento_id: str,
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo_validacion, "seleccionar")),
):
    perito = crud_peritos.obtener_perito(db, a_object_id(perito_id))
    if perito is None:
        raise HTTPException(status_code=404, detail="Perito no encontrado")
    return _url_documento(perito, documento_id)


@router.get(
    "/admin/peritos",
    summary="Peritos por estado (p. ej. PENDIENTE_VALIDACION)",
    description="RF-15",
)
def listar_peritos(
    estado: EstadoCredencial | None = None,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo_validacion, "seleccionar")),
):
    datos, total = crud_peritos.listar_por_estado(db, estado, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.post(
    "/admin/peritos/{perito_id}/validacion",
    response_model=PeritoOut,
    summary="Aprobar o rechazar, con documentos revisados",
    description="RF-15, RF-16",
)
def validar_credenciales(
    perito_id: str,
    validacion: ValidacionCreate,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo_validacion, "actualizar")),
):
    perito = crud_peritos.validar(
        db,
        a_object_id(perito_id),
        validacion.decision,
        validacion.motivo,
        validacion.documentos_revisados,
        actor_usuario(admin),
    )
    if perito is None:
        raise HTTPException(status_code=404, detail="Perito no encontrado")
    if perito["estado_credencial"] == "VALIDADO":
        # RF-49: al validar un perito se reparten las solicitudes pendientes, de la más antigua a la más nueva
        servicio_inspecciones.repartir_pendientes(db)
    return serializar(perito)


@router.post(
    "/admin/peritos/{perito_id}/inconsistencia",
    response_model=PeritoOut,
    summary="Marcar credenciales inconsistentes",
    description="RNF-15",
)
def marcar_inconsistencia(
    perito_id: str,
    datos: InconsistenciaCreate,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo_validacion, "actualizar")),
):
    perito = crud_peritos.marcar_inconsistente(db, a_object_id(perito_id), datos.motivo, actor_usuario(admin))
    if perito is None:
        raise HTTPException(status_code=404, detail="Perito no encontrado")
    return serializar(perito)


@router.post(
    "/interno/peritos/vencimientos",
    summary="Tarea diaria de n8n: matrículas vencidas",
    description="RNF-15",
    dependencies=[Depends(requiere_servicio_n8n)],
)
def marcar_vencimientos(db: Database = Depends(get_db)):
    return {"peritos_vencidos": crud_peritos.marcar_vencidos(db)}
