"""Módulo H con el Diseño DataBase v3: asignación automática, estados de la solicitud, firma y constancia."""

from datetime import timedelta

import pytest
from bson import ObjectId

from app.servicios import inspecciones as servicio
from core.fechas import ahora
from tests.conftest import CONTRASENA, N8N, iniciar_sesion, registrar
from tests.test_flujo_sismo import SISMO, perito_validado, solicitud_valida

DATOS = {
    "fecha_inspeccion": "2026-10-12T14:00:00Z",
    "motivo": "Evaluación posterior al sismo",
    "observaciones": "Observación reservada (RNF-38)",
    "hallazgos": "Fisura en el revoque",
    "resultado": "No compromete la estructura",
}


def nuevo_inmueble(cliente, cabecera) -> str:
    datos = {
        "tipo_inmueble": "CASA",
        "direccion": "Carrera 7 #10-20",
        "ciudad": "Pereira",
        "anio_construccion": 1990,
        "sistema_constructivo": "PORTICOS_CONCRETO",
        "numero_pisos": 2,
        "longitud": -75.70,
        "latitud": 4.81,
    }
    return cliente.post("/inmuebles", json=datos, headers=cabecera).json()["id"]


def solicitar(cliente, inmueble_id, cabecera) -> dict:
    r = cliente.post(f"/inmuebles/{inmueble_id}/solicitudes-inspeccion", json=solicitud_valida(), headers=cabecera)
    assert r.status_code == 201, r.text
    return r.json()


def firmar(cliente, inspeccion_id, cabecera, meses: int = 6) -> dict:
    r = cliente.post(
        f"/inspecciones/{inspeccion_id}/firma",
        json={"contrasena": CONTRASENA, "vigencia_meses": meses},
        headers=cabecera,
    )
    assert r.status_code == 200, r.text
    return r.json()


# --- Solicitud (RF-48, RF-72, BD-03, BD-05) ---------------------------------------------


def test_la_solicitud_exige_tipo_motivo_y_fecha_propuesta(cliente, propietario, inmueble):
    ruta = f"/inmuebles/{inmueble['id']}/solicitudes-inspeccion"
    assert cliente.post(ruta, json={"motivo": "Fisura en el muro"}, headers=propietario).status_code == 422
    ayer = (ahora() - timedelta(days=2)).isoformat()
    r = cliente.post(ruta, json={**solicitud_valida(), "fecha_propuesta": ayer}, headers=propietario)
    assert r.status_code == 400
    r = cliente.post(ruta, json={**solicitud_valida(), "tipo_inspeccion": "PREVENTIVA"}, headers=propietario)
    assert r.status_code == 422  # tipos de RF-48: POSTERIOR_SISMO, SEGUIMIENTO, DANO_REPORTADO


def test_en_estado_1_se_crea_sin_cambiar_el_estado(cliente, db, propietario, inmueble):
    solicitud = solicitar(cliente, inmueble["id"], propietario)

    assert solicitud["estado"] == "PENDIENTE_ASIGNACION"
    assert db["inmuebles"].find_one()["estado"]["codigo"] == 1  # BD-03 (propuesta): 1 → 4 no está permitido
    assert db["notificaciones"].find_one({"tipo": "CAMBIO_SOLICITUD"}) is not None


def test_maximo_una_solicitud_abierta_por_inmueble(cliente, propietario, inmueble):
    solicitar(cliente, inmueble["id"], propietario)
    r = cliente.post(
        f"/inmuebles/{inmueble['id']}/solicitudes-inspeccion", json=solicitud_valida(), headers=propietario
    )
    assert r.status_code == 409 and r.json()["codigo"] == "REGLA_INSPECCION"


def test_no_existe_asignacion_manual(cliente, admin, propietario, inmueble):
    solicitud = solicitar(cliente, inmueble["id"], propietario)
    r = cliente.post(
        f"/admin/solicitudes-inspeccion/{solicitud['id']}/asignacion", json={"perito_id": "x"}, headers=admin
    )
    assert r.status_code in (404, 405)
    assert cliente.get("/admin/solicitudes-inspeccion", headers=admin).json()["total"] == 1  # el admin consulta


# --- Asignación automática (RF-49; 12.3) ------------------------------------------------


def test_asigna_al_perito_con_menos_asignadas_y_desempata_por_la_mas_antigua(cliente, db, admin, propietario):
    perito_a, id_a = perito_validado(cliente, admin, "a@correo.com", "MP-1")
    perito_b, id_b = perito_validado(cliente, admin, "b@correo.com", "MP-2")
    inmuebles = [nuevo_inmueble(cliente, propietario) for _ in range(3)]

    primera = solicitar(cliente, inmuebles[0], propietario)
    segunda = solicitar(cliente, inmuebles[1], propietario)
    tercera = solicitar(cliente, inmuebles[2], propietario)

    # Empate en 0 y nadie ha recibido una: va primero el de _id menor (A); luego B, que tiene 0
    assert primera["perito_id"] == id_a
    assert segunda["perito_id"] == id_b
    # Empate en 1: la recibe quien lleva más tiempo sin recibir una (A)
    assert tercera["perito_id"] == id_a
    assert tercera["asignacion"] == {
        **tercera["asignacion"],
        "metodo": "AUTOMATICA",
        "solicitudes_activas_del_perito": 1,
    }
    usuario_a = db["peritos"].find_one({"_id": ObjectId(id_a)})["usuario_id"]
    assert db["notificaciones"].count_documents({"usuario_id": usuario_a, "tipo": "SOLICITUD_ASIGNADA"}) == 2


def test_las_atendidas_no_cuentan(cliente, db, admin, propietario):
    perito_a, id_a = perito_validado(cliente, admin, "a@correo.com", "MP-1")
    casa = nuevo_inmueble(cliente, propietario)
    solicitud = solicitar(cliente, casa, propietario)
    inspeccion = cliente.post(f"/solicitudes-inspeccion/{solicitud['id']}/inspeccion", json=DATOS, headers=perito_a)
    firmar(cliente, inspeccion.json()["id"], perito_a)
    perito_b, id_b = perito_validado(cliente, admin, "b@correo.com", "MP-2")

    # A tiene 0 ASIGNADA (su única está ATENDIDA) y B 0: empate; B nunca recibió una y va primero
    nueva = solicitar(cliente, nuevo_inmueble(cliente, propietario), propietario)
    assert nueva["perito_id"] == id_b


def test_sin_peritos_queda_pendiente_y_al_validar_se_reparte_la_mas_antigua_primero(cliente, db, admin, propietario):
    vieja = solicitar(cliente, nuevo_inmueble(cliente, propietario), propietario)
    nueva = solicitar(cliente, nuevo_inmueble(cliente, propietario), propietario)
    assert vieja["estado"] == nueva["estado"] == "PENDIENTE_ASIGNACION"

    _, perito_id = perito_validado(cliente, admin)

    vieja = db["solicitudes_inspeccion"].find_one({"_id": ObjectId(vieja["id"])})
    nueva = db["solicitudes_inspeccion"].find_one({"_id": ObjectId(nueva["id"])})
    assert vieja["estado"] == nueva["estado"] == "ASIGNADA"
    assert vieja["asignacion"]["solicitudes_activas_del_perito"] == 0
    assert nueva["asignacion"]["solicitudes_activas_del_perito"] == 1


@pytest.mark.sin_validar  # inserta a mano documentos de prueba incompletos
def test_si_otra_asignacion_gana_se_vuelve_a_elegir(db, cliente, admin, propietario, monkeypatch):
    _, perito_id = perito_validado(cliente, admin)
    solicitud = {
        "inmueble_id": ObjectId(),
        "solicitada_por": ObjectId(),
        "estado": "PENDIENTE_ASIGNACION",
        "creado_en": ahora(),
        "cambios_estado": [],
    }
    solicitud_id = db["solicitudes_inspeccion"].insert_one(solicitud).inserted_id
    llamadas = []
    original = servicio.crud_peritos.marcar_asignacion

    def primera_falla(*args, **kwargs):
        llamadas.append(1)
        return False if len(llamadas) == 1 else original(*args, **kwargs)

    monkeypatch.setattr(servicio.crud_peritos, "marcar_asignacion", primera_falla)

    asignada = servicio.asignar_automaticamente(db, solicitud_id)

    assert asignada["perito_id"] == ObjectId(perito_id) and len(llamadas) == 2


# --- Firma, constancia y vistas (RF-52 a RF-58, RNF-38) -----------------------------------


@pytest.fixture
def asignada(cliente, admin, propietario, inmueble):
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)  # estado 2
    perito, perito_id = perito_validado(cliente, admin)
    solicitud = solicitar(cliente, inmueble["id"], propietario)
    assert solicitud["estado"] == "ASIGNADA"
    return {"perito": perito, "perito_id": perito_id, "solicitud": solicitud, "inmueble_id": inmueble["id"]}


def test_firma_sin_solicitud_no_guarda_nada(db, cliente, asignada):
    r = cliente.post(
        f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=asignada["perito"]
    )
    inspeccion_id = ObjectId(r.json()["id"])
    db["solicitudes_inspeccion"].delete_many({})
    perito = db["peritos"].find_one()
    usuario = {"_id": perito["usuario_id"]}

    with pytest.raises(servicio.ReglaInspeccion):
        servicio.firmar(db, db["inspecciones"].find_one({"_id": inspeccion_id}), 6, usuario)

    assert db["inspecciones"].find_one({"_id": inspeccion_id})["firma"] is None


def test_sismo_con_solicitud_abierta_la_firma_no_cambia_el_estado(cliente, db, asignada):
    """BD-04 (propuesta): un sismo devolvió el inmueble al 2; la firma se guarda y el estado no cambia."""
    r = cliente.post(
        f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=asignada["perito"]
    )
    otro_sismo = {**SISMO, "id_externo": "SGC2026otro", "fecha_hora": "2026-10-20T10:00:00Z"}
    cliente.post("/interno/sismos", json=otro_sismo, headers=N8N)
    assert db["inmuebles"].find_one()["estado"]["codigo"] == 2

    firmada = firmar(cliente, r.json()["id"], asignada["perito"])

    assert firmada["constancia"] is not None
    assert db["inmuebles"].find_one()["estado"]["codigo"] == 2
    assert db["solicitudes_inspeccion"].find_one()["estado"] == "ATENDIDA"


def test_la_constancia_conserva_los_datos_del_perito_al_firmar(cliente, db, asignada):
    r = cliente.post(
        f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=asignada["perito"]
    )
    codigo = firmar(cliente, r.json()["id"], asignada["perito"])["constancia"]["codigo"]
    db["peritos"].update_one({}, {"$set": {"matricula_profesional": "MP-CAMBIADA"}})

    verificacion = cliente.get(f"/constancias/{codigo}").json()

    assert verificacion["perito"]["matricula_profesional"] == "MP-102938475"
    assert verificacion["integra"] is True


def test_vigencia_menor_a_seis_meses(cliente, asignada):
    r = cliente.post(
        f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=asignada["perito"]
    )
    firmada = firmar(cliente, r.json()["id"], asignada["perito"], meses=3)
    assert firmada["constancia"]["vigencia_meses"] == 3
    malo = cliente.post(
        f"/inspecciones/{r.json()['id']}/firma",
        json={"contrasena": CONTRASENA, "vigencia_meses": 7},
        headers=asignada["perito"],
    )
    assert malo.status_code == 422


def test_otro_perito_asignado_despues_no_ve_las_observaciones(cliente, db, admin, propietario, asignada):
    r = cliente.post(
        f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=asignada["perito"]
    )
    firmar(cliente, r.json()["id"], asignada["perito"])
    otro, _ = perito_validado(cliente, admin, "otro.perito@correo.com", "MP-9")
    nueva = solicitar(cliente, asignada["inmueble_id"], propietario)
    assert nueva["perito_id"] != asignada["perito_id"]  # el primero tiene 0 activas, pero el otro nunca recibió

    vista_otro = cliente.get(f"/inspecciones/{r.json()['id']}", headers=otro).json()
    vista_dueno = cliente.get(f"/inspecciones/{r.json()['id']}", headers=propietario).json()
    vista_admin = cliente.get(f"/inspecciones/{r.json()['id']}", headers=admin).json()

    assert vista_otro["observaciones"] is None  # RNF-38
    assert vista_dueno["observaciones"] == vista_admin["observaciones"] == DATOS["observaciones"]


def test_solo_el_perito_asignado_registra(cliente, admin, asignada):
    otro, _ = perito_validado(cliente, admin, "otro.perito@correo.com", "MP-9")
    r = cliente.post(f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=otro)
    assert r.status_code in (403, 409)


def test_no_se_corrige_dos_veces_la_misma_version(cliente, asignada):
    perito = asignada["perito"]
    r = cliente.post(f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=perito)
    firmar(cliente, r.json()["id"], perito)
    assert cliente.post(f"/inspecciones/{r.json()['id']}/correccion", json={}, headers=perito).status_code == 201
    assert cliente.post(f"/inspecciones/{r.json()['id']}/correccion", json={}, headers=perito).status_code == 409


def test_el_vencimiento_de_una_version_reemplazada_no_cambia_el_estado(cliente, db, asignada):
    perito = asignada["perito"]
    r = cliente.post(f"/solicitudes-inspeccion/{asignada['solicitud']['id']}/inspeccion", json=DATOS, headers=perito)
    firmar(cliente, r.json()["id"], perito)
    v2 = cliente.post(f"/inspecciones/{r.json()['id']}/correccion", json={"resultado": "Corregido"}, headers=perito)
    firmar(cliente, v2.json()["id"], perito)
    vencida = ahora() - timedelta(days=1)
    db["inspecciones"].update_one({"version": 1}, {"$set": {"constancia.vigente_hasta": vencida}})

    resumen = cliente.post("/interno/constancias/vencimientos", headers=N8N).json()

    assert resumen["inmuebles_a_estado_1"] == 0
    assert db["inmuebles"].find_one()["estado"]["codigo"] == 5


def test_verificacion_publica_tiene_limite_por_ip(cliente, redis_falso):
    for _ in range(30):
        assert cliente.get("/constancias/NOEXISTE00000000").status_code == 404
    assert cliente.get("/constancias/NOEXISTE00000000").status_code == 429


def test_el_perito_no_asignado_no_ve_el_inmueble(cliente, admin, propietario, inmueble):
    perito, _ = perito_validado(cliente, admin)
    assert cliente.get(f"/inmuebles/{inmueble['id']}", headers=perito).status_code == 403
    registrar(cliente, "x@correo.com")
    assert (
        cliente.get(f"/inmuebles/{inmueble['id']}", headers=iniciar_sesion(cliente, "x@correo.com")).status_code == 403
    )
