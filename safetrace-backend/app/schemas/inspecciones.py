"""Modelos Pydantic de entrada y salida de H · Inspecciones y constancias (RF-48 a RF-58, RF-72).

Nombres y estados del Diseño DataBase v3 (secciones 9.1 y 9.2) y de la ERS v2.1.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.bitacora import ArchivoEntrada

EstadoSolicitud = Literal["PENDIENTE_ASIGNACION", "ASIGNADA", "ATENDIDA"]  # RF-72
TipoInspeccion = Literal["POSTERIOR_SISMO", "SEGUIMIENTO", "DANO_REPORTADO"]  # RF-48


# --- Solicitudes --------------------------------------------------------------


class SolicitudCreate(BaseModel):
    """RF-48: tipo de inspección, motivo y fecha propuesta, los tres obligatorios."""

    tipo_inspeccion: TipoInspeccion
    motivo: str = Field(min_length=5, max_length=500)
    fecha_propuesta: datetime


class CambioSolicitud(BaseModel):
    estado: EstadoSolicitud
    fecha: datetime


class Asignacion(BaseModel):
    metodo: Literal["AUTOMATICA"]
    fecha: datetime
    solicitudes_activas_del_perito: int


class SolicitudOut(BaseModel):
    id: str
    inmueble_id: str
    solicitada_por: str
    motivo: str
    tipo_inspeccion: TipoInspeccion
    fecha_propuesta: datetime
    estado: EstadoSolicitud
    perito_id: str | None = None
    asignacion: Asignacion | None = None
    cambios_estado: list[CambioSolicitud] = []
    creado_en: datetime


class SolicitudPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[SolicitudOut]


# --- Inspecciones -------------------------------------------------------------


class InspeccionBase(BaseModel):
    fecha_inspeccion: datetime
    motivo: str = Field(min_length=5, max_length=500)
    observaciones: str = Field(min_length=3, max_length=5000)
    hallazgos: str = Field(min_length=3, max_length=5000)
    resultado: str = Field(min_length=3, max_length=5000)


class InspeccionCreate(InspeccionBase):
    evidencias: list[ArchivoEntrada] = Field(default=[], max_length=30)


class InspeccionUpdate(BaseModel):
    """Solo antes de firmar."""

    fecha_inspeccion: datetime | None = None
    motivo: str | None = Field(default=None, min_length=5, max_length=500)
    observaciones: str | None = Field(default=None, min_length=3, max_length=5000)
    hallazgos: str | None = Field(default=None, min_length=3, max_length=5000)
    resultado: str | None = Field(default=None, min_length=3, max_length=5000)


class CorreccionCreate(InspeccionUpdate):
    evidencias: list[ArchivoEntrada] = Field(default=[], max_length=30)  # se suman a las de la versión anterior


class FirmaCreate(BaseModel):
    contrasena: str  # el perito firma confirmando su contraseña (RF-52)
    vigencia_meses: int = Field(default=6, ge=1, le=6)  # 6 o menos (RF-54, RF-55)


class PeritoFirmante(BaseModel):
    nombre_completo: str
    profesion: str
    matricula_profesional: str


class Firma(BaseModel):
    fecha: datetime
    metodo: Literal["CONFIRMACION_CONTRASENA"]
    perito: PeritoFirmante  # copia al firmar (M-06)
    huella_sha256: str


class Constancia(BaseModel):
    codigo: str
    emitida_en: datetime
    vigencia_meses: int
    vigente_hasta: datetime


class InspeccionOut(BaseModel):
    """Constancia completa (RF-57). `observaciones` llega vacía a quien no es propietario,
    perito firmante ni administrador (RNF-38)."""

    id: str
    solicitud_id: str
    inmueble_id: str
    perito_id: str
    version: int
    version_anterior_id: str | None = None
    fecha_inspeccion: datetime
    motivo: str
    observaciones: str | None = None
    hallazgos: str
    resultado: str
    evidencias_ids: list[str] = []
    firma: Firma | None = None  # null en borrador
    constancia: Constancia | None = None
    estado_constancia: Literal["VIGENTE", "VENCIDA"] | None = None  # calculado al leer (RF-56)
    es_version_activa: bool  # calculado: la versión firmada de número mayor
    reemplazada_por_version: int | None = None
    aviso_legal: str
    creado_en: datetime


class InmueblePublico(BaseModel):
    tipo_inmueble: str | None = None
    ciudad: str | None = None


class PeritoPublico(BaseModel):
    nombre_completo: str
    matricula_profesional: str


class VerificacionOut(BaseModel):
    """Lo que ve cualquiera que escanea el QR (RF-58, BD-06). Nunca observaciones, hallazgos, resultado,
    estado del inmueble, dirección ni datos del propietario (RNF-18, RNF-19, RNF-38)."""

    existe: bool
    codigo: str
    inmueble: InmueblePublico
    perito: PeritoPublico
    fecha_firma: datetime
    vigente_hasta: datetime
    estado: Literal["VIGENTE", "VENCIDA"]
    integra: bool  # la huella recalculada coincide con la firmada
    version: int
    reemplazada_por_version: int | None = None
    aviso_legal: str
