"""Migraciones 0001 a 0009 (Diseño DataBase v3, sección 14). Dueño: Nicolás (BD).

mongomock no aplica validadores ni conoce collMod: aquí se prueba la parte de datos, que la simulación
no escribe, que repetir no cambia nada y que se detienen ante datos que debe corregir una persona.
El paso de collMod se reemplaza por un registro de llamadas; se prueba de verdad contra safetrace_test.
"""

import importlib
from datetime import UTC, datetime

import pytest
from bson import ObjectId

from db import migraciones, validacion, validadores

NOMBRES = [
    "0001_quitar_borrar_en_historial",
    "0002_crear_validadores",
    "0003_indices",
    "0004_recuperaciones",
    "0005_notificaciones",
    "0006_revisiones",
    "0007_eventos",
    "0008_peritos_modulos_configuracion",
    "0009_modulo_h",
]


@pytest.fixture(autouse=True)
def revisar_en_python(monkeypatch):
    """mongomock no conoce $jsonSchema: se cuenta con el mismo evaluador que usa conftest."""

    def revisar(db):
        return {
            c: sum(1 for d in db[c].find() if validacion.errores(d, validadores.cargar(c)))
            for c in validadores.COLECCIONES
        }

    monkeypatch.setattr(migraciones, "revisar", revisar)


def _cargar(nombre):
    return importlib.import_module(f"db.migraciones.{nombre}")


@pytest.fixture
def validadores_aplicados(monkeypatch):
    aplicados: list[str] = []

    def registrar(db, coleccion, aplicar):
        if aplicar:
            aplicados.append(coleccion)

    for nombre in NOMBRES:
        modulo = _cargar(nombre)
        if hasattr(modulo, "aplicar_validador"):
            monkeypatch.setattr(modulo, "aplicar_validador", registrar)
    return aplicados


def _foto(db) -> dict:
    return {c: sorted(map(str, db[c].find({}))) for c in db.list_collection_names()}


def test_simulacion_no_escribe(db, validadores_aplicados):
    antes = _foto(db)
    for nombre in NOMBRES:
        _cargar(nombre).migrar(db, aplicar=False)
    assert _foto(db) == antes
    assert validadores_aplicados == []


def test_todas_se_aplican_y_se_pueden_repetir(db, validadores_aplicados):
    for nombre in NOMBRES:
        _cargar(nombre).migrar(db, aplicar=True)
    despues = _foto(db)
    for nombre in NOMBRES:
        _cargar(nombre).migrar(db, aplicar=True)
    assert _foto(db) == despues
    assert len(set(validadores_aplicados)) == 24


@pytest.mark.sin_validar
def test_0001_quita_borrar_en_historial(db):
    db["permisos"].update_one({"rol": "SUPERADMIN", "modulo": "auditoria"}, {"$set": {"borrar": True}})
    _cargar(NOMBRES[0]).migrar(db, aplicar=True)
    assert db["permisos"].count_documents({"modulo": "auditoria", "borrar": True}) == 0


def test_0005_notificaciones_viejas_salieron_por_correo(db, validadores_aplicados):
    db["notificaciones"].insert_one(
        {
            "usuario_id": ObjectId(),
            "tipo": "CAMBIO_SOLICITUD",
            "estado": "ENVIADA",
            "schema_version": 2,
            "creado_en": datetime.now(UTC),
        }
    )
    _cargar("0005_notificaciones").migrar(db, aplicar=True)
    assert db["notificaciones"].find_one({})["canales"] == ["CORREO"]
    assert "leida_en" not in db["notificaciones"].find_one({})


@pytest.mark.sin_validar
def test_0008_se_detiene_si_un_perito_no_tiene_especialidad(db, validadores_aplicados):
    db["peritos"].insert_one({"usuario_id": None, "especialidad": ""})
    with pytest.raises(migraciones.MigracionDetenida, match="especialidad"):
        _cargar("0008_peritos_modulos_configuracion").migrar(db, aplicar=True)
    assert validadores_aplicados == []


def test_0008_completa_peritos_permisos_y_configuracion(db, validadores_aplicados):
    db["configuracion"].update_one({"_id": "parametros_sismo"}, {"$unset": {"emparejamiento": ""}})
    db["permisos"].update_one(
        {"rol": "ADMINISTRADOR_GENERAL", "modulo": "asignacion_peritos"}, {"$set": {"actualizar": True}}
    )
    db["modulos"].update_many({}, {"$unset": {"modulo_ers": ""}})
    _cargar("0008_peritos_modulos_configuracion").migrar(db, aplicar=True)
    assert db["configuracion"].find_one({"_id": "parametros_sismo"})["emparejamiento"]
    permiso = db["permisos"].find_one({"rol": "ADMINISTRADOR_GENERAL", "modulo": "asignacion_peritos"})
    assert permiso["actualizar"] is False
    assert db["modulos"].count_documents({"modulo_ers": {"$exists": False}}) == 0


@pytest.mark.sin_validar
def test_0009_se_detiene_con_estados_viejos(db, validadores_aplicados):
    db["solicitudes_inspeccion"].insert_one({"estado": "SOLICITADA"})
    with pytest.raises(migraciones.MigracionDetenida, match="solicitudes_inspeccion"):
        _cargar("0009_modulo_h").migrar(db, aplicar=False)


def test_aplicar_validador_usa_collmod_si_la_coleccion_existe(db, monkeypatch):
    llamadas = []
    monkeypatch.setattr(type(db), "command", lambda self, *a, **k: llamadas.append((a, k)))
    migraciones.aplicar_validador(db, "usuarios", aplicar=True)
    ((argumentos, opciones),) = llamadas
    assert argumentos == ("collMod", "usuarios")
    assert opciones["validationLevel"] == "strict" and opciones["validationAction"] == "error"
    assert "$jsonSchema" in opciones["validator"]


def test_semillas_no_crean_un_usuario_con_correo_que_la_api_rechaza(db, capsys):
    from db import semillas

    semillas._crear_usuario_inicial(db, "superadmin@safetrace.local", "Clave-larga-123", "SUPERADMIN", "Superadmin")
    assert db["usuarios"].count_documents({"correo": "superadmin@safetrace.local"}) == 0
    assert "no creado" in capsys.readouterr().out
