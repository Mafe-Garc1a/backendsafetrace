"""Modelos Pydantic de entrada y salida de D · Bitácora y evidencias (RF-22 a RF-27)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.peritos import Archivo

# EVENTO_EXTERNO solo lo registra el sistema cuando llega un sismo (RF-36)
TipoEventoUsuario = Literal["MANTENIMIENTO", "DANO", "REPARACION", "INTERVENCION"]
CategoriaDocumento = Literal["FACTURA", "ORDEN_TRABAJO", "CONTRATO", "INFORME_TECNICO"]


class EventoBase(BaseModel):
    tipo: TipoEventoUsuario
    fecha_evento: datetime
    descripcion: str = Field(min_length=5, max_length=2000)
    zona_id: str | None = None  # catálogo cerrado `zonas`


class EventoCreate(EventoBase):
    pass


class Invalidacion(BaseModel):
    usuario_id: str
    fecha: datetime
    motivo: str


class EventoOut(BaseModel):
    id: str
    inmueble_id: str
    tipo: str
    fecha_evento: datetime
    descripcion: str
    zona_id: str | None = None
    origen: Literal["USUARIO", "SISTEMA"]
    sismo_id: str | None = None
    # Diseño DataBase v3, 8.1: un evento equivocado se marca, nunca se edita ni se borra (RNF-16)
    estado: Literal["VIGENTE", "INVALIDO", "REEMPLAZADO"] = "VIGENTE"
    reemplazado_por: str | None = None
    invalidacion: Invalidacion | None = None
    registrado_por: str | None = None
    creado_en: datetime


class InvalidacionEventoCreate(BaseModel):
    estado: Literal["INVALIDO", "REEMPLAZADO"]
    motivo: str = Field(min_length=5, max_length=500)
    reemplazado_por: str | None = None

    @model_validator(mode="after")
    def reemplazo_con_evento(self):
        if self.estado == "REEMPLAZADO" and not self.reemplazado_por:
            raise ValueError("Indique el evento que lo reemplaza (reemplazado_por)")
        return self


class ArchivoEntrada(BaseModel):
    """Foto o documento ya subido al proveedor que se adjunta a un evento, revisión o inspección."""

    tipo_archivo: Literal["FOTO", "DOCUMENTO"] = "FOTO"
    categoria_documento: CategoriaDocumento | None = None
    zona_id: str | None = None
    archivo: Archivo

    @model_validator(mode="after")
    def categoria_solo_en_documentos(self):
        if self.tipo_archivo == "FOTO" and self.categoria_documento is not None:
            raise ValueError("categoria_documento solo aplica a documentos")
        return self


class EvidenciaCreate(ArchivoEntrada):
    evento_id: str  # las evidencias de revisiones e inspecciones llegan con su registro


class Origen(BaseModel):
    tipo: Literal["EVENTO", "REVISION", "INSPECCION"]
    id: str


class Invalidacion(BaseModel):
    usuario_id: str
    fecha: datetime
    motivo: str


class EvidenciaOut(BaseModel):
    id: str
    inmueble_id: str
    origen: Origen
    tipo_archivo: str
    categoria_documento: str | None = None
    zona_id: str | None = None
    archivo: Archivo
    estado: Literal["VIGENTE", "INVALIDA", "REEMPLAZADA"]
    reemplazada_por: str | None = None
    invalidacion: Invalidacion | None = None
    cargado_por: str
    creado_en: datetime


class InvalidacionCreate(BaseModel):
    estado: Literal["INVALIDA", "REEMPLAZADA"]
    motivo: str = Field(min_length=5, max_length=500)
    reemplazada_por: str | None = None

    @model_validator(mode="after")
    def reemplazo_con_evidencia(self):
        if self.estado == "REEMPLAZADA" and not self.reemplazada_por:
            raise ValueError("Indique la evidencia que la reemplaza (reemplazada_por)")
        return self


TipoContenido = Literal["image/jpeg", "image/png", "image/webp", "application/pdf"]

# La extensión sale del tipo de contenido, nunca del nombre que envía el usuario
EXTENSIONES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


class AutorizacionSubidaCreate(BaseModel):
    inmueble_id: str
    nombre_archivo: str = Field(min_length=1, max_length=120)  # solo informativo
    tipo_contenido: TipoContenido
    tamano_bytes: int = Field(gt=0)  # queda firmado: el proveedor rechaza un archivo de otro tamaño


class AutorizacionSubidaOut(BaseModel):
    """El navegador hace `PUT url_subida` con `encabezados` y el archivo como cuerpo, antes de `expira_en`.
    Luego registra la evidencia con `ruta` y la huella SHA-256 calculada en el navegador."""

    ruta: str
    url_subida: str
    metodo: Literal["PUT"]
    encabezados: dict[str, str]
    expira_en: datetime


class UrlArchivoOut(BaseModel):
    """URL temporal para ver o descargar un archivo; pedir otra cuando venza."""

    url: str
    expira_en: datetime


class EventoLinea(EventoOut):
    evidencias: list[EvidenciaOut] = []


class LineaCronologicaPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[EventoLinea]
