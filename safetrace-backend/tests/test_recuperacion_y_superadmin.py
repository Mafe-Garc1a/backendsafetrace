"""RF-73 (recuperación de contraseña), RF-74 (superadministrador) y permisos de historial."""

from datetime import timedelta

import pytest

from app.crud import modulo_permisos
from core import email
from core.fechas import ahora
from tests.conftest import CONTRASENA, iniciar_sesion, registrar
from trabajador.tareas import enviar_correo

NUEVA = "Otra-contrasena-2"


@pytest.fixture
def correos(monkeypatch):
    """Captura los correos que enviaría el trabajador."""
    enviados = []
    monkeypatch.setattr(email, "enviar", lambda destino, plantilla, datos: enviados.append((destino, plantilla, datos)))
    return enviados


def _procesar_correos(db):
    for tarea in db["tareas"].find({"tipo": "ENVIAR_CORREO", "estado": "PENDIENTE"}):
        enviar_correo.ejecutar(db, tarea)
        db["tareas"].update_one({"_id": tarea["_id"]}, {"$set": {"estado": "COMPLETADA"}})


def _token_del_correo(correos) -> str:
    return correos[-1][2]["enlace"].split("token=", 1)[1]


def test_la_respuesta_es_la_misma_exista_o_no_el_correo(cliente, db):
    registrar(cliente, "ana@correo.com")

    existe = cliente.post("/auth/recuperacion", json={"correo": "ana@correo.com"})
    no_existe = cliente.post("/auth/recuperacion", json={"correo": "nadie@correo.com"})

    assert existe.status_code == no_existe.status_code == 202
    assert existe.json() == no_existe.json()
    assert db["recuperaciones_contrasena"].count_documents({}) == 1


def test_el_token_en_claro_nunca_se_guarda(cliente, db, correos):
    registrar(cliente, "ana@correo.com")
    cliente.post("/auth/recuperacion", json={"correo": "ana@correo.com"})
    _procesar_correos(db)

    token = _token_del_correo(correos)
    assert correos[-1][0] == "ana@correo.com"
    assert correos[-1][1] == "RECUPERAR_CONTRASENA"
    assert token not in str(list(db["recuperaciones_contrasena"].find()))
    assert token not in str(list(db["tareas"].find()))


def test_restablecer_es_de_un_solo_uso_y_cierra_las_sesiones(cliente, db, correos):
    registrar(cliente, "ana@correo.com")
    sesion = iniciar_sesion(cliente, "ana@correo.com")
    cliente.post("/auth/recuperacion", json={"correo": "ana@correo.com"})
    _procesar_correos(db)
    token = _token_del_correo(correos)

    r = cliente.post("/auth/recuperacion/restablecer", json={"token": token, "contrasena_nueva": NUEVA})
    assert r.status_code == 204

    assert cliente.get("/auth/yo", headers=sesion).status_code == 401
    assert cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": NUEVA}).status_code == 200
    otra = cliente.post("/auth/recuperacion/restablecer", json={"token": token, "contrasena_nueva": "Tercera-clave-3"})
    assert otra.status_code == 400
    assert otra.json()["codigo"] == "ENLACE_INVALIDO"
    registro = db["auditoria"].find_one({"accion": "RESTABLECER_CONTRASENA"})
    assert registro is not None
    assert "ana@correo.com" not in str(registro)  # RNF-20


def test_enlace_vencido_no_sirve(cliente, db, correos):
    registrar(cliente, "ana@correo.com")
    cliente.post("/auth/recuperacion", json={"correo": "ana@correo.com"})
    _procesar_correos(db)
    db["recuperaciones_contrasena"].update_many({}, {"$set": {"expira_en": ahora() - timedelta(minutes=1)}})

    r = cliente.post(
        "/auth/recuperacion/restablecer", json={"token": _token_del_correo(correos), "contrasena_nueva": NUEVA}
    )

    assert r.status_code == 400


def test_maximo_tres_solicitudes_por_usuario_por_hora(cliente, db):
    registrar(cliente, "ana@correo.com")
    for _ in range(4):
        assert cliente.post("/auth/recuperacion", json={"correo": "ana@correo.com"}).status_code == 202

    assert db["recuperaciones_contrasena"].count_documents({}) == 3


def test_con_redis_maximo_cinco_solicitudes_por_ip_por_hora(cliente, redis_falso):
    for i in range(5):
        assert cliente.post("/auth/recuperacion", json={"correo": f"p{i}@correo.com"}).status_code == 202

    r = cliente.post("/auth/recuperacion", json={"correo": "otra@correo.com"})

    assert r.status_code == 429
    assert r.headers["Retry-After"] == "3600"


# --- RF-74: superadministrador ---------------------------------------------------


def test_solo_el_superadmin_crea_administradores(cliente, db, admin, superadmin, correos):
    datos = {"nombre_completo": "Nueva Administradora", "correo": "nueva.admin@safetrace.co"}

    assert cliente.post("/admin/administradores", json=datos, headers=admin).status_code == 403
    r = cliente.post("/admin/administradores", json=datos, headers=superadmin)

    assert r.status_code == 201, r.text
    assert r.json()["rol"] == "ADMINISTRADOR_GENERAL"
    _procesar_correos(db)
    assert correos[-1][0] == "nueva.admin@safetrace.co"  # recibe el enlace para elegir su contraseña
    registro = db["auditoria"].find_one({"accion": "REGISTRAR_USUARIO", "cambios.rol": "ADMINISTRADOR_GENERAL"})
    assert registro["actor"]["rol"] == "SUPERADMIN"


def test_el_administrador_solo_cambia_entre_propietario_y_perito(cliente, db, admin):
    usuario = registrar(cliente, "ana@correo.com")
    ruta = f"/admin/usuarios/{usuario['id']}/rol"

    assert cliente.patch(ruta, json={"rol": "PERITO"}, headers=admin).json()["rol"] == "PERITO"
    assert cliente.patch(ruta, json={"rol": "ADMINISTRADOR_GENERAL"}, headers=admin).status_code == 403


def test_el_administrador_no_desactiva_a_otro_administrador(cliente, db, admin, superadmin):
    datos = {"nombre_completo": "Otra Administradora", "correo": "otra.admin@safetrace.co"}
    otro = cliente.post("/admin/administradores", json=datos, headers=superadmin).json()
    ruta = f"/admin/usuarios/{otro['id']}/estado"

    assert cliente.patch(ruta, json={"activo": False}, headers=admin).status_code == 403
    assert cliente.patch(ruta, json={"activo": False}, headers=superadmin).json()["activo"] is False


# --- Historial: nadie tiene borrar (Diseño DataBase v3) -------------------------------


def test_ningun_rol_tiene_borrar_en_los_modulos_de_historial(db):
    con_borrar = db["permisos"].count_documents(
        {"modulo": {"$in": list(modulo_permisos.MODULOS_SOLO_AGREGAR)}, "borrar": True}
    )
    assert con_borrar == 0


def test_no_se_puede_dar_borrar_sobre_el_historial(cliente, superadmin):
    r = cliente.put("/admin/permisos/bitacora/ADMINISTRADOR_GENERAL", json={"borrar": True}, headers=superadmin)

    assert r.status_code == 400
    assert r.json()["codigo"] == "BORRAR_NO_PERMITIDO"


def test_contrasena_original_sigue_si_no_se_usa_el_enlace(cliente, db):
    registrar(cliente, "ana@correo.com")
    cliente.post("/auth/recuperacion", json={"correo": "ana@correo.com"})

    assert cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA}).status_code == 200
