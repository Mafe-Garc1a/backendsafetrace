"""Rutas de A · Cuentas: registro, inicio y cierre de sesión, recuperación de contraseña.

RF-01 a RF-03, RF-07, RF-73. El inicio de sesión y la recuperación tienen límite de intentos en Redis
(Integración Redis v2, 6.3; RC-2026-010).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.database import Database

from app.crud import permisos as crud_permisos
from app.crud import roles as crud_roles
from app.crud import usuarios as crud_usuarios
from app.router.dependencies import authenticate_user, get_current_user, oauth2_scheme
from app.schemas.auth import ResponseLoggin, Restablecimiento, SolicitudRecuperacion
from app.schemas.permisos import PermisoBase
from app.schemas.usuarios import UsuarioCreate, UsuarioOut
from core import limite
from core.config import settings
from core.database import get_db, serializar
from core.security import create_access_token, hash_token

router = APIRouter()


@router.post(
    "/registro",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registro con correo, contraseña y consentimiento de datos",
    description="RF-01, RF-07",
)
def registrar_usuario(usuario: UsuarioCreate, db: Database = Depends(get_db)):
    if not usuario.acepta_politica:
        raise HTTPException(status_code=400, detail="Debe aceptar la política de tratamiento de datos")
    creado = crud_usuarios.crear_usuario(db, usuario, usuario.rol)
    return serializar(creado)


@router.post(
    "/sesion",
    response_model=ResponseLoggin,
    summary="Inicio de sesión (en `username` va el correo)",
    description="RF-02",
)
def iniciar_sesion(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Database = Depends(get_db),
):
    ip = limite.ip_de(request)
    # Antes de bcrypt: protege las contraseñas y el procesador (5 fallos por IP y correo, 30 por IP en 15 min)
    limite.login_bloqueado(ip, form_data.username)
    usuario = authenticate_user(form_data.username, form_data.password, db)
    if not usuario:
        limite.login_fallido(ip, form_data.username)
        raise HTTPException(
            status_code=401,
            detail="Datos incorrectos en correo o contraseña",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario["activo"]:
        raise HTTPException(status_code=403, detail="Usuario inactivo. No autorizado")
    # Como en avisena: un rol inactivo no puede iniciar sesión
    if not crud_roles.rol_activo(db, usuario["rol"]):
        raise HTTPException(status_code=401, detail="Rol inactivo")

    limite.login_exitoso(ip, form_data.username)
    data = {"sub": str(usuario["_id"]), "rol": usuario["rol"]}
    access_token = create_access_token(data)
    crud_usuarios.crear_sesion(db, usuario["_id"], hash_token(access_token))

    usuario.pop("contrasena_hash")
    return ResponseLoggin(
        usuario=serializar(usuario),
        access_token=access_token,
        minutos_inactividad=settings.minutos_sesion,
    )


@router.delete(
    "/sesion",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cierre de sesión",
    description="RF-03",
)
def cerrar_sesion(
    token: str = Depends(oauth2_scheme),
    _: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    crud_usuarios.cerrar_sesion(db, hash_token(token))


@router.get("/yo", response_model=UsuarioOut, summary="Usuario de la sesión actual")
def usuario_actual(usuario: dict = Depends(get_current_user)):
    return serializar(usuario)


@router.get(
    "/yo/permisos",
    response_model=list[PermisoBase],
    summary="Permisos del rol de la sesión actual (para armar el menú del frontend)",
)
def permisos_actuales(usuario: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    return crud_permisos.permisos_de_rol(db, usuario["rol"])


RESPUESTA_RECUPERACION = {"mensaje": "Si el correo está registrado, recibirá un enlace para restablecer la contraseña"}


@router.post(
    "/recuperacion",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pedir un enlace para restablecer la contraseña",
    description="RF-73. La respuesta es la misma exista o no el correo. Máximo 5 por hora por IP y 3 por usuario.",
    dependencies=[Depends(limite.limite_recuperar())],
)
def solicitar_recuperacion(solicitud: SolicitudRecuperacion, db: Database = Depends(get_db)):
    crud_usuarios.solicitar_recuperacion(db, solicitud.correo)
    return RESPUESTA_RECUPERACION


@router.post(
    "/recuperacion/restablecer",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Restablecer la contraseña con el enlace (un solo uso, 60 minutos)",
    description="RF-73. Cierra todas las sesiones abiertas del usuario.",
)
def restablecer_contrasena(datos: Restablecimiento, db: Database = Depends(get_db)):
    crud_usuarios.restablecer_contrasena(db, datos.token, datos.contrasena_nueva)
