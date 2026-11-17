"""Servicios del Módulo H · Inspecciones y constancias (RF-48 a RF-58, RF-72). Dueño: Juan Miguel.

Capa de reglas del negocio (Estructura del backend v2, sección 2): el router llama a este archivo y este
archivo llama a los crud. Diseño: ERS v2.1 y Diseño DataBase v3 (secciones 9.1, 9.2, 12.3 y 12.4).

Reglas clave:
- Solicitud (RF-48): tipo, motivo y fecha propuesta obligatorios. Nace en PENDIENTE_ASIGNACION y lleva el
  inmueble del estado 2 o 3 al 4 (RF-41). En el 1 o el 5 se crea sin cambiar el estado (BD-03, propuesta).
  Máximo una solicitud abierta por inmueble (BD-05).
- Asignación automática (RF-49): el perito VALIDADO con menos solicitudes ASIGNADA; empate → el que lleva
  más tiempo sin recibir una (null primero). Sin peritos validados queda pendiente; cuando un perito pasa a
  VALIDADO se reparten las pendientes, de la más antigua a la más nueva. No hay asignación manual (R-24).
- Solo el perito VALIDADO y asignado registra y firma (RNF-14, RNF-15); firma confirmando su contraseña.
- Firmar es una transacción (12.4): firma y constancia, solicitud → ATENDIDA, inmueble 4 → 5 si sigue en 4
  (BD-04: si no, el estado no cambia) y aviso CONSTANCIA_DISPONIBLE.
- Firmada = inmutable (RNF-13). Corregir crea la versión siguiente en borrador (RF-53); al firmarse recibe
  código propio y hasta seis meses de vigencia desde su firma (RF-54, RF-55).
- Vigente o vencida, versión activa y reemplazada se calculan al leer; no se guardan.
- Verificación pública (RF-58, BD-06): nunca observaciones, hallazgos, resultado, estado, dirección ni
  datos del propietario (RNF-18, RNF-19, RNF-38).
"""

from datetime import UTC, datetime, timedelta, timezone

from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import auditoria
from app.crud import bitacora as crud_bitacora
from app.crud import estados as crud_estados
from app.crud import inmuebles as crud_inmuebles
from app.crud import inspecciones as crud
from app.crud import notificaciones as crud_notificaciones
from app.crud import peritos as crud_peritos
from app.crud import usuarios as crud_usuarios
from app.crud.estados import EstadoInmueble as E
from app.schemas.inspecciones import CorreccionCreate, InspeccionCreate, InspeccionUpdate, SolicitudCreate
from core.database import en_transaccion
from core.errores import ErrorNegocio, TransicionRechazada
from core.fechas import ahora, en_utc, sumar_meses

AVISO_LEGAL = (
    "Esta inspección no certifica el cumplimiento de la NSR-10 ni la habitabilidad del inmueble. "
    "Registra la evaluación del perito que la firma, quien responde por su juicio técnico. "
    "SafeTrace solo garantiza que el documento no ha sido alterado desde su firma."
)
METODO_FIRMA = "CONFIRMACION_CONTRASENA"
INTENTOS_ASIGNACION = 3
ACTOR_ASIGNACION = {"tipo": "PROCESO", "id": "asignacion-automatica"}
ACTOR_VENCIMIENTOS = {"tipo": "PROCESO", "id": "vencimientos-n8n"}
HORA_COLOMBIA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano
# Desde estos estados, solicitar lleva el inmueble al 4 (RF-41)
ESTADOS_QUE_PASAN_A_4 = (E.MARCADO_POR_EVENTO_SISMICO, E.REVISION_PROPIETARIO_REGISTRADA)


class ReglaInspeccion(ErrorNegocio):
    """La acción no está permitida por las reglas del módulo H."""

    codigo = "REGLA_INSPECCION"


class DatoInvalido(ErrorNegocio):
    status = 400
    codigo = "DATO_INVALIDO"


def _referencia_solicitud(solicitud_id: ObjectId) -> dict:
    return {"tipo": "SOLICITUD_INSPECCION", "id": solicitud_id}


# --- Solicitudes (RF-48, RF-49, RF-69, RF-72) -------------------------------------------


def crear_solicitud(db: Database, inmueble: dict, datos: SolicitudCreate, usuario: dict) -> dict:
    """El propietario solicita una inspección y el sistema intenta asignarla de inmediato."""
    if crud.hay_solicitud_abierta(db, inmueble["_id"]):
        raise ReglaInspeccion("El inmueble ya tiene una solicitud de inspección en curso")
    hoy = ahora().astimezone(HORA_COLOMBIA).date()
    if en_utc(datos.fecha_propuesta).astimezone(HORA_COLOMBIA).date() < hoy:
        raise DatoInvalido("La fecha propuesta no puede ser anterior a hoy")

    momento = ahora()
    documento = {
        "inmueble_id": inmueble["_id"],
        "solicitada_por": usuario["_id"],
        "motivo": datos.motivo,
        "tipo_inspeccion": datos.tipo_inspeccion,
        "fecha_propuesta": en_utc(datos.fecha_propuesta),
        "estado": crud.ESTADO_PENDIENTE,
        "perito_id": None,
        "asignacion": None,
        "cambios_estado": [{"estado": crud.ESTADO_PENDIENTE, "fecha": momento}],
        "schema_version": 3,
        "creado_en": momento,
    }
    actor = auditoria.actor_usuario(usuario)
    estado_actual = inmueble["estado"]["codigo"]

    def operacion(session):
        solicitud = crud.insertar_solicitud(db, dict(documento), session=session)
        if estado_actual in ESTADOS_QUE_PASAN_A_4:
            crud_estados.pedir_transicion(
                db, inmueble["_id"], estado_actual, E.INSPECCION_SOLICITADA, "INSPECCION_SOLICITADA",
                _referencia_solicitud(solicitud["_id"]), actor, session=session,
            )  # fmt: skip
        crud_notificaciones.notificar(
            db, inmueble["propietario_id"], "CAMBIO_SOLICITUD", _referencia_solicitud(solicitud["_id"]), session
        )
        auditoria.registrar(
            db, "solicitudes_inspeccion", solicitud["_id"], "SOLICITAR_INSPECCION", actor,
            {"tipo_inspeccion": datos.tipo_inspeccion}, session=session,
        )  # fmt: skip
        return solicitud

    solicitud = en_transaccion(db, operacion)
    return asignar_automaticamente(db, solicitud["_id"]) or solicitud


def _elegir_perito(db: Database) -> tuple[dict, int] | None:
    """Menos solicitudes ASIGNADA; empate → ultima_asignacion_en más antigua o null (12.3, paso 1)."""
    candidatos = crud_peritos.candidatos_asignacion(db)
    if not candidatos:
        return None
    conteo = crud.asignadas_por_perito(db, [p["_id"] for p in candidatos])

    def orden(perito):
        ultima = perito.get("ultima_asignacion_en")
        return (conteo.get(perito["_id"], 0), ultima is not None, ultima or datetime.min.replace(tzinfo=UTC))

    elegido = min(candidatos, key=orden)
    return elegido, conteo.get(elegido["_id"], 0)


def asignar_automaticamente(db: Database, solicitud_id: ObjectId) -> dict | None:
    """Asigna la solicitud pendiente al perito que corresponde (RF-49). None si no hay perito o ya no está pendiente.

    Si otra asignación toma al mismo perito a la vez, la condición sobre `ultima_asignacion_en` falla y se vuelve
    a elegir, hasta 3 veces (12.3, paso 2). Perito, solicitud y avisos van en una sola transacción (paso 3).
    """
    for _ in range(INTENTOS_ASIGNACION):
        eleccion = _elegir_perito(db)
        if eleccion is None:
            return None
        perito, activas = eleccion

        def operacion(session, perito=perito, activas=activas):
            momento = ahora()
            if not crud_peritos.marcar_asignacion(
                db, perito["_id"], perito.get("ultima_asignacion_en"), momento, session=session
            ):
                return "REINTENTAR"
            solicitud = crud.marcar_asignada(db, solicitud_id, perito["_id"], activas, momento, session=session)
            if solicitud is None:
                # Ya no estaba pendiente: se deshace la marca del perito saliendo de la transacción con error
                raise _SolicitudYaAsignada()
            referencia = _referencia_solicitud(solicitud_id)
            crud_notificaciones.notificar(db, perito["usuario_id"], "SOLICITUD_ASIGNADA", referencia, session)
            crud_notificaciones.notificar(db, solicitud["solicitada_por"], "CAMBIO_SOLICITUD", referencia, session)
            auditoria.registrar(
                db, "solicitudes_inspeccion", solicitud_id, "ASIGNAR_PERITO", ACTOR_ASIGNACION,
                {"perito_id": perito["_id"], "solicitudes_activas_del_perito": activas}, session=session,
            )  # fmt: skip
            return solicitud

        try:
            resultado = en_transaccion(db, operacion)
        except _SolicitudYaAsignada:
            return None
        if resultado != "REINTENTAR":
            return resultado
    return None


class _SolicitudYaAsignada(Exception):
    """Interna: aborta la transacción de asignación sin dejar marcado al perito."""


def repartir_pendientes(db: Database) -> int:
    """Asigna las solicitudes pendientes, de la más antigua a la más nueva (RF-49). Devuelve cuántas asignó.

    La llama B cuando un perito pasa a VALIDADO. Se detiene en cuanto una no se puede asignar
    (no hay peritos validados).
    """
    asignadas = 0
    for solicitud in crud.pendientes_mas_antiguas(db):
        if asignar_automaticamente(db, solicitud["_id"]) is None:
            break
        asignadas += 1
    return asignadas


def obtener_solicitud(db: Database, solicitud_id: ObjectId) -> dict | None:
    return crud.obtener_solicitud(db, solicitud_id)


def listar_solicitudes(db: Database, filtros: dict, saltar: int, limite: int) -> tuple[list[dict], int]:
    return crud.listar_solicitudes(db, filtros, saltar, limite)


# --- Inspecciones (RF-50 a RF-53) ---------------------------------------------------------


def perito_validado_de(db: Database, usuario: dict) -> dict:
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    if perito is None or perito["estado_credencial"] != "VALIDADO":
        raise ReglaInspeccion("Solo un perito con credenciales VALIDADAS puede registrar y firmar (RNF-14)")
    return perito


def _verificar_autor(db: Database, inspeccion: dict, usuario: dict) -> dict:
    perito = perito_validado_de(db, usuario)
    if inspeccion["perito_id"] != perito["_id"]:
        raise ReglaInspeccion("Solo el perito asignado puede modificar o firmar esta inspección")
    return perito


def _registrar_evidencias(db, inspeccion_id, inmueble_id, entradas, usuario) -> list[ObjectId]:
    return [
        crud_bitacora.registrar_evidencia(db, inmueble_id, "INSPECCION", inspeccion_id, entrada, usuario)["_id"]
        for entrada in entradas
    ]


def _nueva_version(db, base: dict, version: int, anterior_id, campos: dict, usuario: dict, evidencias) -> dict:
    documento = {
        "solicitud_id": base["solicitud_id"],
        "inmueble_id": base["inmueble_id"],
        "perito_id": base["perito_id"],
        "version": version,
        "version_anterior_id": anterior_id,
        **campos,
        "evidencias_ids": list(base.get("evidencias_ids", [])),
        "firma": None,
        "constancia": None,
        "aviso_legal": AVISO_LEGAL,
        "schema_version": 3,
        "creado_en": ahora(),
    }
    try:
        documento = crud.insertar_inspeccion(db, documento)
    except DuplicateKeyError:
        raise ReglaInspeccion("Ya existe esa versión de la inspección") from None
    nuevas = _registrar_evidencias(db, documento["_id"], documento["inmueble_id"], evidencias, usuario)
    if nuevas:
        crud.agregar_evidencias(db, documento["_id"], nuevas)
        documento["evidencias_ids"] += nuevas
    return documento


def registrar_inspeccion(db: Database, solicitud: dict, datos: InspeccionCreate, usuario: dict) -> dict:
    """El perito validado y asignado registra la inspección (RF-50, RF-51). Queda en borrador."""
    perito = perito_validado_de(db, usuario)
    if solicitud["estado"] != crud.ESTADO_ASIGNADA or solicitud["perito_id"] != perito["_id"]:
        raise ReglaInspeccion("La solicitud no está asignada a este perito")
    if crud.versiones_de_solicitud(db, solicitud["_id"]):
        raise ReglaInspeccion("La inspección ya fue registrada; edítela antes de firmar o corrija la versión firmada")
    crud_bitacora.validar_rutas(solicitud["inmueble_id"], datos.evidencias)
    base = {"solicitud_id": solicitud["_id"], "inmueble_id": solicitud["inmueble_id"], "perito_id": perito["_id"]}
    campos = datos.model_dump(exclude={"evidencias"})
    documento = _nueva_version(db, base, 1, None, campos, usuario, datos.evidencias)
    auditoria.registrar(db, "inspecciones", documento["_id"], "REGISTRAR_INSPECCION", auditoria.actor_usuario(usuario))
    return documento


def obtener_inspeccion(db: Database, inspeccion_id: ObjectId) -> dict | None:
    return crud.obtener_inspeccion(db, inspeccion_id)


def editar_borrador(db: Database, inspeccion: dict, cambios: InspeccionUpdate, usuario: dict) -> dict:
    """Antes de firmar, el perito puede ajustar su registro (RNF-13)."""
    _verificar_autor(db, inspeccion, usuario)
    datos = cambios.model_dump(exclude_unset=True, exclude_none=True)
    if not datos:
        return inspeccion
    actualizada = crud.actualizar_borrador(db, inspeccion["_id"], datos)
    if actualizada is None:
        raise ReglaInspeccion("Una inspección firmada no se modifica; registre una corrección (RNF-13)")
    return actualizada


def _codigo_libre(db: Database) -> str:
    codigo = crud.generar_codigo()
    while crud.codigo_en_uso(db, codigo):
        codigo = crud.generar_codigo()
    return codigo


def firmar(db: Database, inspeccion: dict, vigencia_meses: int, usuario: dict) -> dict:
    """Firma, calcula la huella y emite la constancia en una transacción (RF-52, RF-54, RF-55, RF-57; 12.4)."""
    perito = _verificar_autor(db, inspeccion, usuario)
    if inspeccion.get("firma") is not None:
        raise ReglaInspeccion("La inspección ya está firmada")
    solicitud = crud.obtener_solicitud(db, inspeccion["solicitud_id"])
    if solicitud is None:
        raise ReglaInspeccion("La solicitud de esta inspección ya no existe")
    usuario_perito = crud_usuarios.obtener_usuario(db, perito["usuario_id"])

    momento = ahora()
    firma = {
        "fecha": momento,
        "metodo": METODO_FIRMA,
        # Copia al firmar: si el perito cambia su perfil, la constancia no cambia (M-06)
        "perito": {
            "nombre_completo": usuario_perito["nombre_completo"],
            "profesion": perito["profesion"],
            "matricula_profesional": perito["matricula_profesional"],
        },
        "huella_sha256": None,
    }
    constancia = {
        "codigo": _codigo_libre(db),
        "emitida_en": momento,
        "vigencia_meses": vigencia_meses,
        "vigente_hasta": sumar_meses(momento, vigencia_meses),
    }
    firma["huella_sha256"] = crud.huella_contenido(crud.contenido_firmable(inspeccion, firma, constancia))
    actor = auditoria.actor_usuario(usuario)

    def operacion(session):
        firmada = crud.guardar_firma(db, inspeccion["_id"], firma, constancia, session=session)
        if firmada is None:
            raise ReglaInspeccion("La inspección ya está firmada")
        crud.marcar_atendida(db, solicitud["_id"], momento, session=session)  # una corrección ya está ATENDIDA
        estado = crud_estados.consultar_estado(db, inspeccion["inmueble_id"])
        if estado and estado["codigo"] == E.INSPECCION_SOLICITADA:
            try:
                crud_estados.pedir_transicion(
                    db, inspeccion["inmueble_id"], E.INSPECCION_SOLICITADA, E.INSPECCION_FIRMADA,
                    "INSPECCION_FIRMADA", {"tipo": "INSPECCION", "id": inspeccion["_id"]}, actor, session=session,
                )  # fmt: skip
            except TransicionRechazada:
                pass  # BD-04: otro proceso cambió el estado (p. ej. un sismo); la firma se guarda igual
        referencia = {"tipo": "INSPECCION", "id": inspeccion["_id"]}
        crud_notificaciones.notificar(db, solicitud["solicitada_por"], "CONSTANCIA_DISPONIBLE", referencia, session)
        auditoria.registrar(
            db, "inspecciones", inspeccion["_id"], "FIRMAR_INSPECCION", actor,
            {"firma.huella_sha256": firma["huella_sha256"], "version": inspeccion["version"]}, session=session,
        )  # fmt: skip
        return firmada

    return en_transaccion(db, operacion)


def crear_correccion(db: Database, inspeccion: dict, datos: CorreccionCreate, usuario: dict) -> dict:
    """Versión siguiente, en borrador, de la versión firmada y activa (RF-53, RNF-13)."""
    _verificar_autor(db, inspeccion, usuario)
    versiones = crud.versiones_de_solicitud(db, inspeccion["solicitud_id"])
    if inspeccion.get("firma") is None or versiones[0]["_id"] != inspeccion["_id"]:
        raise ReglaInspeccion("Solo se corrige la versión firmada más reciente; termine antes el borrador pendiente")
    crud_bitacora.validar_rutas(inspeccion["inmueble_id"], datos.evidencias)
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True, exclude={"evidencias"})
    campos = {
        campo: cambios.get(campo, inspeccion[campo])
        for campo in ("fecha_inspeccion", "motivo", "observaciones", "hallazgos", "resultado")
    }
    version = inspeccion["version"] + 1
    documento = _nueva_version(db, inspeccion, version, inspeccion["_id"], campos, usuario, datos.evidencias)
    auditoria.registrar(
        db, "inspecciones", documento["_id"], "CORREGIR_INSPECCION", auditoria.actor_usuario(usuario),
        {"version_anterior_id": inspeccion["_id"], "version": version},
    )  # fmt: skip
    return documento


# --- Vistas calculadas al leer (RF-56, RF-57, RNF-38) --------------------------------------


estado_constancia = crud.estado_constancia
_version_activa = crud.version_activa
_reemplazo = crud.reemplazo


def puede_ver_observaciones(db: Database, inspeccion: dict, usuario: dict, inmueble: dict, supervisa: bool) -> bool:
    """Propietario, perito firmante y administrador (RNF-38)."""
    if inmueble["propietario_id"] == usuario["_id"] or supervisa:
        return True
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    return perito is not None and perito["_id"] == inspeccion["perito_id"]


def vista(db: Database, inspeccion: dict, usuario: dict, inmueble: dict, supervisa: bool, versiones=None) -> dict:
    """Inspección con estado de la constancia, versión activa y reemplazo calculados (RF-57)."""
    versiones = versiones if versiones is not None else crud.versiones_de_solicitud(db, inspeccion["solicitud_id"])
    activa = _version_activa(versiones)
    resultado = {
        **inspeccion,
        "estado_constancia": estado_constancia(inspeccion),
        "es_version_activa": activa is not None and activa["_id"] == inspeccion["_id"],
        "reemplazada_por_version": _reemplazo(versiones, inspeccion),
    }
    if not puede_ver_observaciones(db, inspeccion, usuario, inmueble, supervisa):
        resultado["observaciones"] = None
    return resultado


def vistas_de_inmueble(db: Database, inmueble: dict, usuario: dict, supervisa: bool) -> list[dict]:
    inspecciones = crud.listar_de_inmueble(db, inmueble["_id"])
    por_solicitud: dict = {}
    for inspeccion in inspecciones:
        por_solicitud.setdefault(inspeccion["solicitud_id"], []).append(inspeccion)
    return [
        vista(db, i, usuario, inmueble, supervisa, versiones=por_solicitud[i["solicitud_id"]]) for i in inspecciones
    ]


def constancias_activas(db: Database, inmueble_id: ObjectId) -> list[dict]:
    """Versión activa de cada solicitud del inmueble, con el estado de su constancia. La usa I."""
    return crud.constancias_activas(db, inmueble_id)


# --- Verificación pública y vencimiento (RF-44, RF-56, RF-58) -------------------------------


def verificar(db: Database, codigo: str) -> dict | None:
    """Vista fija para cualquiera, sin cuenta (RF-58; Diseño DataBase v3, 9.2 y BD-06)."""
    inspeccion = crud.obtener_por_codigo(db, codigo.strip().upper())
    if inspeccion is None:
        return None
    inmueble = crud_inmuebles.datos_publicos(db, inspeccion["inmueble_id"])
    versiones = crud.versiones_de_solicitud(db, inspeccion["solicitud_id"])
    constancia = inspeccion["constancia"]
    firma = inspeccion["firma"]
    return {
        "existe": True,
        "codigo": constancia["codigo"],
        "inmueble": {"tipo_inmueble": inmueble.get("tipo_inmueble"), "ciudad": inmueble.get("ciudad")},
        "perito": {
            "nombre_completo": firma["perito"]["nombre_completo"],
            "matricula_profesional": firma["perito"]["matricula_profesional"],
        },
        "fecha_firma": firma["fecha"],
        "vigente_hasta": constancia["vigente_hasta"],
        "estado": estado_constancia(inspeccion),
        "integra": crud.es_integra(inspeccion),
        "version": inspeccion["version"],
        "reemplazada_por_version": _reemplazo(versiones, inspeccion),
        "aviso_legal": inspeccion["aviso_legal"],
    }


def vencer_constancias(db: Database) -> dict:
    """Tarea diaria de n8n (RF-44, RF-56). No escribe en inspecciones: el vencimiento se calcula al leer.

    Solo pide a G el paso 5 → 1 si el inmueble sigue en el 5 y la constancia vencida es la de la versión
    activa de su solicitud (9.2). Así, una corrección firmada después mantiene el inmueble en el 5.
    """
    momento = ahora()
    revisadas = 0
    a_estado_1 = 0
    for inspeccion in crud.firmadas_vencidas(db, momento):
        revisadas += 1
        activa = _version_activa(crud.versiones_de_solicitud(db, inspeccion["solicitud_id"]))
        if activa is None or activa["_id"] != inspeccion["_id"]:
            continue
        estado = crud_estados.consultar_estado(db, inspeccion["inmueble_id"])
        if not estado or estado["codigo"] != E.INSPECCION_FIRMADA:
            continue
        try:
            crud_estados.pedir_transicion(
                db, inspeccion["inmueble_id"], E.INSPECCION_FIRMADA, E.SIN_EVENTO_PENDIENTE, "CONSTANCIA_VENCIDA",
                {"tipo": "INSPECCION", "id": inspeccion["_id"]}, ACTOR_VENCIMIENTOS,
            )  # fmt: skip
        except TransicionRechazada:
            continue
        a_estado_1 += 1
        auditoria.registrar(
            db, "inspecciones", inspeccion["_id"], "VENCER_CONSTANCIA", ACTOR_VENCIMIENTOS,
            {"vigente_hasta": inspeccion["constancia"]["vigente_hasta"]},
        )  # fmt: skip
    return {"constancias_vencidas_revisadas": revisadas, "inmuebles_a_estado_1": a_estado_1}
