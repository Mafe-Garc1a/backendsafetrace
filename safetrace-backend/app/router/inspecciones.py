"""Rutas de H · Inspecciones y constancias (RF-48 a RF-58, RF-72). Dueño: Juan Miguel.

Las reglas están en `app/servicios/inspecciones.py`. No hay ruta de asignación manual: la asignación
es automática (RF-49, R-24) y el administrador solo consulta (`asignacion_peritos: seleccionar`).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import peritos as crud_peritos
from app.crud import usuarios as crud_usuarios
from app.router.comunes import validar_zona
from app.router.dependencies import (
    get_current_user,
    obtener_inmueble_autorizado,
    puede_supervisar,
    requiere_permiso,
    requiere_servicio_n8n,
)
from app.schemas.inspecciones import (
    CorreccionCreate,
    EstadoSolicitud,
    FirmaCreate,
    InspeccionCreate,
    InspeccionOut,
    InspeccionUpdate,
    SolicitudCreate,
    SolicitudOut,
    SolicitudPage,
    VerificacionOut,
)
from app.servicios import inspecciones as servicio
from core import limite
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina
from core.security import verificar_contrasena

router = APIRouter()
modulo = "inspecciones"
modulo_solicitudes = "solicitudes_inspeccion"
modulo_asignacion = "asignacion_peritos"


def _obtener_solicitud(db: Database, solicitud_id: str) -> dict:
    solicitud = servicio.obtener_solicitud(db, a_object_id(solicitud_id))
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


def _obtener_inspeccion(db: Database, inspeccion_id: str, usuario: dict) -> tuple[dict, dict]:
    inspeccion = servicio.obtener_inspeccion(db, a_object_id(inspeccion_id))
    if inspeccion is None:
        raise HTTPException(status_code=404, detail="Inspección no encontrada")
    inmueble = obtener_inmueble_autorizado(db, inspeccion["inmueble_id"], usuario)
    return inspeccion, inmueble


def _vista(db: Database, inspeccion: dict, usuario: dict, inmueble: dict) -> dict:
    return serializar(servicio.vista(db, inspeccion, usuario, inmueble, puede_supervisar(db, usuario)))


# --- Solicitudes ----------------------------------------------------------------


@router.post(
    "/inmuebles/{inmueble_id}/solicitudes-inspeccion",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    summary="El propietario solicita una inspección; el sistema asigna el perito",
    description="RF-41, RF-48, RF-49, RF-72",
)
def solicitar_inspeccion(
    inmueble_id: str,
    solicitud: SolicitudCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo_solicitudes, "insertar")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    return serializar(servicio.crear_solicitud(db, inmueble, solicitud, usuario))


@router.get(
    "/inmuebles/{inmueble_id}/solicitudes-inspeccion",
    response_model=SolicitudPage,
    summary="Solicitudes de inspección del inmueble",
    description="RF-48, RF-69, RF-72",
)
def listar_solicitudes_inmueble(
    inmueble_id: str,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    filtros = {"inmueble_id": inmueble["_id"]}
    datos, total = servicio.listar_solicitudes(db, filtros, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.get(
    "/admin/solicitudes-inspeccion",
    response_model=SolicitudPage,
    summary="Solicitudes por estado y su asignación automática (solo consulta)",
    description="RF-49, RF-72",
)
def listar_solicitudes(
    estado: EstadoSolicitud | None = None,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo_asignacion, "seleccionar")),
):
    filtros = {"estado": estado} if estado else {}
    datos, total = servicio.listar_solicitudes(db, filtros, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.get(
    "/peritos/solicitudes",
    response_model=SolicitudPage,
    summary="Bandeja del perito: solicitudes asignadas y atendidas",
    description="RF-49, RF-50",
)
def listar_solicitudes_perito(
    estado: EstadoSolicitud | None = None,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    if perito is None:
        raise HTTPException(status_code=404, detail="Primero registre su perfil profesional")
    filtros = {"perito_id": perito["_id"], **({"estado": estado} if estado else {})}
    datos, total = servicio.listar_solicitudes(db, filtros, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


# --- Inspecciones -----------------------------------------------------------------


@router.post(
    "/solicitudes-inspeccion/{solicitud_id}/inspeccion",
    response_model=InspeccionOut,
    status_code=status.HTTP_201_CREATED,
    summary="El perito asignado registra la inspección (borrador)",
    description="RF-50, RF-51",
)
def registrar_inspeccion(
    solicitud_id: str,
    inspeccion: InspeccionCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    solicitud = _obtener_solicitud(db, solicitud_id)
    for evidencia in inspeccion.evidencias:
        validar_zona(db, evidencia.zona_id)
    inmueble = obtener_inmueble_autorizado(db, solicitud["inmueble_id"], usuario)
    registrada = servicio.registrar_inspeccion(db, solicitud, inspeccion, usuario)
    return _vista(db, registrada, usuario, inmueble)


@router.get(
    "/inmuebles/{inmueble_id}/inspecciones",
    response_model=list[InspeccionOut],
    summary="Inspecciones del inmueble con todas sus versiones",
    description="RF-50, RF-53, RF-57, RNF-38",
)
def listar_inspecciones(inmueble_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    return serializar(servicio.vistas_de_inmueble(db, inmueble, usuario, puede_supervisar(db, usuario)))


@router.get(
    "/inspecciones/{inspeccion_id}",
    response_model=InspeccionOut,
    summary="Detalle de una inspección y su constancia",
    description="RF-50, RF-57, RNF-38",
)
def obtener_inspeccion(inspeccion_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    inspeccion, inmueble = _obtener_inspeccion(db, inspeccion_id, usuario)
    return _vista(db, inspeccion, usuario, inmueble)


@router.put(
    "/inspecciones/{inspeccion_id}",
    response_model=InspeccionOut,
    summary="Editar la inspección antes de firmarla",
    description="RF-50, RNF-13",
)
def editar_inspeccion(
    inspeccion_id: str,
    cambios: InspeccionUpdate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    inspeccion, inmueble = _obtener_inspeccion(db, inspeccion_id, usuario)
    return _vista(db, servicio.editar_borrador(db, inspeccion, cambios, usuario), usuario, inmueble)


@router.post(
    "/inspecciones/{inspeccion_id}/firma",
    response_model=InspeccionOut,
    summary="Firmar con contraseña y emitir la constancia",
    description="RF-42, RF-52, RF-54, RF-55, RF-57, RF-70",
)
def firmar_inspeccion(
    inspeccion_id: str,
    firma: FirmaCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    inspeccion, inmueble = _obtener_inspeccion(db, inspeccion_id, usuario)
    hash_guardado = crud_usuarios.obtener_hash_contrasena(db, usuario["_id"])
    if not hash_guardado or not verificar_contrasena(firma.contrasena, hash_guardado):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta: no se firmó la inspección")
    firmada = servicio.firmar(db, inspeccion, firma.vigencia_meses, usuario)
    return _vista(db, firmada, usuario, inmueble)


@router.post(
    "/inspecciones/{inspeccion_id}/correccion",
    response_model=InspeccionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Nueva versión, en borrador, de una inspección firmada",
    description="RF-53, RNF-13",
)
def corregir_inspeccion(
    inspeccion_id: str,
    correccion: CorreccionCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    inspeccion, inmueble = _obtener_inspeccion(db, inspeccion_id, usuario)
    for evidencia in correccion.evidencias:
        validar_zona(db, evidencia.zona_id)
    return _vista(db, servicio.crear_correccion(db, inspeccion, correccion, usuario), usuario, inmueble)


# --- Constancias --------------------------------------------------------------------


@router.get(
    "/constancias/{codigo}",
    response_model=VerificacionOut,
    summary="Verificación pública por código o QR (sin cuenta)",
    description="RF-56, RF-58. Máximo 30 consultas por minuto por IP (RC-2026-010).",
    dependencies=[Depends(limite.limite_verificar())],
)
def verificar_constancia(codigo: str, db: Database = Depends(get_db)):
    verificacion = servicio.verificar(db, codigo)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="No existe una constancia con ese código")
    return verificacion


@router.post(
    "/interno/constancias/vencimientos",
    summary="Tarea diaria de n8n: inmuebles con constancia vencida vuelven al estado 1",
    description="RF-44, RF-56",
    dependencies=[Depends(requiere_servicio_n8n)],
)
def vencer_constancias(db: Database = Depends(get_db)):
    return servicio.vencer_constancias(db)
