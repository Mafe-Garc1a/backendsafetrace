"""Modelos Pydantic de entrada y salida de A · Cuentas: registro e inicio de sesión."""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.usuarios import UsuarioOut


class ResponseLoggin(BaseModel):
    usuario: UsuarioOut
    access_token: str
    token_type: str = "bearer"
    minutos_inactividad: int


class SolicitudRecuperacion(BaseModel):
    correo: EmailStr


class Restablecimiento(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    contrasena_nueva: str = Field(min_length=8, max_length=72)
