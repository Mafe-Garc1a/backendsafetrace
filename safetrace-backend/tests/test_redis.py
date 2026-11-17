"""Integración con Redis (Integración Redis v2; RC-2026-010): sesiones, permisos, límites y degradación."""

from core import cache, redis_cliente
from core.redis_cliente import clave
from core.security import hash_token
from tests.conftest import CONTRASENA, registrar


def _token(encabezado: dict) -> str:
    return encabezado["Authorization"].split(" ", 1)[1]


def test_iniciar_sesion_guarda_la_sesion_en_redis_y_cerrarla_la_borra(cliente, redis_falso):
    registrar(cliente, "ana@correo.com")
    r = cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA})
    encabezado = {"Authorization": f"Bearer {r.json()['access_token']}"}
    nombre = clave("sesion", hash_token(_token(encabezado)))

    assert redis_falso.exists(nombre)
    assert 0 < redis_falso.ttl(nombre) <= 30 * 60

    assert cliente.delete("/auth/sesion", headers=encabezado).status_code == 204
    assert not redis_falso.exists(nombre)
    assert cliente.get("/auth/yo", headers=encabezado).status_code == 401


def test_redis_responde_sin_leer_mongo_y_mongo_corta_al_renovar(cliente, db, redis_falso):
    registrar(cliente, "ana@correo.com")
    r = cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA})
    encabezado = {"Authorization": f"Bearer {r.json()['access_token']}"}
    token_hash = hash_token(_token(encabezado))

    # La sesión se cerró en MongoDB mientras Redis no se enteraba (riesgo documentado, sección 12)
    db["sesiones"].delete_many({})
    assert cliente.get("/auth/yo", headers=encabezado).status_code == 200

    # A los 5 minutos toca renovar el respaldo: MongoDB ya no la tiene y la sesión se corta
    usuario_id, _ = cache.sesion_leer(token_hash)
    redis_falso.set(clave("sesion", token_hash), f"{usuario_id}|0")
    assert cliente.get("/auth/yo", headers=encabezado).status_code == 401
    assert not redis_falso.exists(clave("sesion", token_hash))


def test_si_redis_se_reinicia_mongo_decide_y_la_sesion_vuelve_a_redis(cliente, propietario, redis_falso):
    token_hash = hash_token(_token(propietario))
    assert not redis_falso.exists(clave("sesion", token_hash))  # se creó antes de conectar Redis

    assert cliente.get("/auth/yo", headers=propietario).status_code == 200
    assert redis_falso.exists(clave("sesion", token_hash))


def test_desactivar_cuenta_borra_sus_sesiones_en_redis(cliente, db, admin, redis_falso):
    registrar(cliente, "ana@correo.com")
    r = cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA})
    encabezado = {"Authorization": f"Bearer {r.json()['access_token']}"}
    usuario = db["usuarios"].find_one({"correo": "ana@correo.com"})

    r = cliente.patch(f"/admin/usuarios/{usuario['_id']}/estado", json={"activo": False}, headers=admin)

    assert r.status_code == 200
    assert not redis_falso.exists(clave("sesion", hash_token(_token(encabezado))))
    assert not redis_falso.exists(clave("usuario_sesiones", usuario["_id"]))


def test_redis_caido_no_tumba_la_api(cliente, propietario):
    class RedisCaido:
        def __getattr__(self, _):
            raise ConnectionError("sin conexión")

    redis_cliente.usar_cliente(RedisCaido())

    assert cliente.get("/auth/yo", headers=propietario).status_code == 200
    # Tras el fallo, Redis queda en pausa 15 s y ni siquiera se intenta
    assert redis_cliente.obtener_redis() is None


def test_permisos_se_cachean_y_se_invalidan_al_cambiarlos(cliente, superadmin, propietario, redis_falso):
    assert cliente.get("/inmuebles", headers=propietario).status_code == 200
    nombre = clave("permiso", "PROPIETARIO", "inmuebles", "seleccionar")
    assert redis_falso.get(nombre) == "1"

    r = cliente.put("/admin/permisos/inmuebles/PROPIETARIO", json={"seleccionar": False}, headers=superadmin)
    assert r.status_code == 200, r.text

    assert not redis_falso.exists(nombre)
    assert cliente.get("/inmuebles", headers=propietario).status_code == 403


def test_cinco_fallos_bloquean_el_par_ip_correo_antes_de_bcrypt(cliente, redis_falso):
    registrar(cliente, "ana@correo.com")
    for _ in range(5):
        r = cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": "incorrecta"})
        assert r.status_code == 401

    r = cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA})

    assert r.status_code == 429
    assert r.headers["Retry-After"] == "900"
    assert r.json()["codigo"] == "DEMASIADAS_PETICIONES"
    # Otro correo desde la misma IP aún puede entrar (el límite de la IP es 30)
    registrar(cliente, "luis@correo.com")
    r = cliente.post("/auth/sesion", data={"username": "luis@correo.com", "password": CONTRASENA})
    assert r.status_code == 200


def test_acierto_reinicia_solo_el_contador_del_par(cliente, redis_falso):
    registrar(cliente, "ana@correo.com")
    for _ in range(4):
        cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": "incorrecta"})

    assert cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA}).status_code == 200

    claves = redis_falso.keys(clave("login*"))
    assert claves == [clave("login_ip", "testclient")]
    assert redis_falso.get(clave("login_ip", "testclient")) == "4"
    # El correo nunca aparece en claro en Redis (RNF-20)
    assert all("ana@correo.com" not in c for c in redis_falso.keys("*"))


def test_sin_redis_no_hay_limite_de_intentos(cliente):
    registrar(cliente, "ana@correo.com")
    for _ in range(7):
        cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": "incorrecta"})

    assert cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA}).status_code == 200
