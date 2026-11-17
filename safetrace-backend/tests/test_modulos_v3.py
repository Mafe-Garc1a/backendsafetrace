"""Cambios de la v3 en D (invalidar eventos), E (cambio calculado), F (emparejamiento) y K (centro de avisos)."""

from bson import ObjectId

from tests.conftest import N8N, iniciar_sesion, registrar
from tests.test_flujo_sismo import SISMO

EVENTO = {"tipo": "DANO", "fecha_evento": "2026-08-10T18:00:00Z", "descripcion": "Fisura en el muro"}


def test_invalidar_un_evento_lo_marca_y_lo_saca_de_ultimos_eventos(cliente, db, propietario, inmueble):
    evento = cliente.post(f"/inmuebles/{inmueble['id']}/eventos", json=EVENTO, headers=propietario).json()
    assert evento["estado"] == "VIGENTE"
    cambio = {"estado": "INVALIDO", "motivo": "Lo registré en el inmueble equivocado"}

    r = cliente.patch(f"/eventos/{evento['id']}/invalidacion", json=cambio, headers=propietario)

    assert r.status_code == 200 and r.json()["estado"] == "INVALIDO"
    assert r.json()["invalidacion"]["motivo"] == cambio["motivo"]
    assert db["inmuebles"].find_one()["ultimos_eventos"] == []
    assert db["eventos"].count_documents({}) == 1  # no se borra
    linea = cliente.get(f"/inmuebles/{inmueble['id']}/linea-cronologica", headers=propietario).json()
    assert linea["datos"][0]["estado"] == "INVALIDO"  # sigue visible con su marca
    assert db["auditoria"].count_documents({"accion": "INVALIDAR_EVENTO"}) == 1
    assert cliente.patch(f"/eventos/{evento['id']}/invalidacion", json=cambio, headers=propietario).status_code == 409


def test_los_eventos_del_sistema_no_se_invalidan(cliente, db, propietario, inmueble):
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)
    externo = db["eventos"].find_one({"tipo": "EVENTO_EXTERNO"})
    cambio = {"estado": "INVALIDO", "motivo": "No me pareció fuerte"}

    r = cliente.patch(f"/eventos/{externo['_id']}/invalidacion", json=cambio, headers=propietario)

    assert r.status_code == 403


def test_un_evento_invalidado_no_cuenta_como_antecedente(cliente, db, propietario, inmueble):
    from app.crud import bitacora

    evento = cliente.post(f"/inmuebles/{inmueble['id']}/eventos", json=EVENTO, headers=propietario).json()
    assert bitacora.antecedentes(db, ObjectId(inmueble["id"]))["antecedentes_danos"] == 1
    cambio = {"estado": "INVALIDO", "motivo": "Duplicado por error"}
    cliente.patch(f"/eventos/{evento['id']}/invalidacion", json=cambio, headers=propietario)

    assert bitacora.antecedentes(db, ObjectId(inmueble["id"]))["antecedentes_danos"] == 0


def test_otro_usuario_no_invalida_eventos_ajenos(cliente, propietario, inmueble):
    evento = cliente.post(f"/inmuebles/{inmueble['id']}/eventos", json=EVENTO, headers=propietario).json()
    registrar(cliente, "otro@correo.com")
    otro = iniciar_sesion(cliente, "otro@correo.com")
    cambio = {"estado": "INVALIDO", "motivo": "No es mío"}
    assert cliente.patch(f"/eventos/{evento['id']}/invalidacion", json=cambio, headers=otro).status_code == 403


def test_la_revision_ya_no_guarda_cambio_estado_aplicado(cliente, db, propietario, inmueble):
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)
    revision = {"observaciones": "La fisura creció", "hubo_cambios": True, "solicitara_inspeccion": True}

    r = cliente.post(f"/inmuebles/{inmueble['id']}/revisiones", json=revision, headers=propietario)

    assert r.json()["cambio_estado_aplicado"] is True
    assert "cambio_estado_aplicado" not in db["revisiones"].find_one()
    lista = cliente.get(f"/inmuebles/{inmueble['id']}/revisiones", headers=propietario).json()
    assert lista["datos"][0]["cambio_estado_aplicado"] is True


def test_una_revision_v2_conserva_su_valor_guardado(cliente, db, propietario, inmueble):
    db["revisiones"].insert_one(
        {
            "inmueble_id": ObjectId(inmueble["id"]),
            "fecha": db["inmuebles"].find_one()["creado_en"],
            "observaciones": "Revisión vieja",
            "hubo_cambios": False,
            "solicitara_inspeccion": False,
            "evidencias_ids": [],
            "cambio_estado_aplicado": True,
            "registrada_por": ObjectId(),
            "schema_version": 2,
            "creado_en": db["inmuebles"].find_one()["creado_en"],
        }
    )
    lista = cliente.get(f"/inmuebles/{inmueble['id']}/revisiones", headers=propietario).json()
    assert lista["datos"][0]["cambio_estado_aplicado"] is True


def test_el_emparejamiento_sale_de_la_configuracion(cliente, db, inmueble):
    db["configuracion"].update_one(
        {"_id": "parametros_sismo"}, {"$set": {"emparejamiento": {"ventana_segundos": 10, "distancia_km": 100}}}
    )
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)
    usgs = {**SISMO, "fuente": "USGS", "id_externo": "us7000q1ab", "fecha_hora": "2026-10-08T03:11:10Z"}

    r = cliente.post("/interno/sismos", json=usgs, headers=N8N).json()

    assert r["resultado"] == "NUEVO"  # 29 s de diferencia > 10 s: son dos sismos
    assert r["sismo"]["parametros_aplicados"] == {"magnitud_minima": 5.0, "radio_afectacion_km": 200}


def test_centro_de_notificaciones(cliente, db, propietario, inmueble):
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)
    lista = cliente.get("/notificaciones", headers=propietario).json()
    assert lista["no_leidas"] == 1 and lista["datos"][0]["canales"] == ["CORREO", "APP"]
    notificacion_id = lista["datos"][0]["id"]

    r = cliente.patch(f"/notificaciones/{notificacion_id}/lectura", headers=propietario)

    assert r.status_code == 200 and r.json()["leida_en"] is not None
    assert cliente.get("/notificaciones/no-leidas", headers=propietario).json() == {"no_leidas": 0}
    registrar(cliente, "otro@correo.com")
    otro = iniciar_sesion(cliente, "otro@correo.com")
    assert cliente.patch(f"/notificaciones/{notificacion_id}/lectura", headers=otro).status_code == 404


def test_marcar_todas_como_leidas(cliente, propietario, inmueble):
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)
    assert cliente.post("/notificaciones/lectura", headers=propietario).status_code == 204
    assert cliente.get("/notificaciones/no-leidas", headers=propietario).json() == {"no_leidas": 0}


def test_una_tarea_solo_la_ve_quien_puede_ver_su_recurso(cliente, db, admin, propietario, inmueble):
    tarea_id = db["tareas"].insert_one(
        {"tipo": "ENVIAR_CORREO", "estado": "PENDIENTE", "datos": {"notificacion_id": ObjectId()}, "intentos": 0,
         "max_intentos": 3, "creado_en": db["inmuebles"].find_one()["creado_en"], "finalizada_en": None}
    ).inserted_id  # fmt: skip

    assert cliente.get(f"/tareas/{tarea_id}", headers=propietario).status_code == 403
    assert cliente.get(f"/tareas/{tarea_id}", headers=admin).status_code == 200
