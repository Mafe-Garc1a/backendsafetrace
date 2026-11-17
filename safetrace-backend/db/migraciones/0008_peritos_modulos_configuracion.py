"""0008 · peritos, modulos y configuracion (Diseño DataBase v3, 6.5, 6.7, 6.8 y 7.1).

Dueños: Brayan (B) y Nicolás (BD).
- peritos: `ultima_asignacion_en` null donde falte (desempate de RF-49). `especialidad` pasa a obligatoria:
  si un perfil no la tiene, la migración se detiene y lista los ids; el dato lo da el perito, no se inventa.
- modulos: `modulo_ers` con el módulo de la ERS de cada uno.
- configuracion: `emparejamiento` {120 s, 100 km} donde falte (RF-32).
- permisos: el administrador general solo consulta asignacion_peritos (la asignación es automática, R-24).
"""

from db.migraciones import MigracionDetenida, aplicar_validador, ejecutar, exigir_que_cumplan
from db.semillas import CONFIGURACION, MODULOS


def migrar(db, aplicar: bool) -> None:
    sin_especialidad = [
        str(p["_id"]) for p in db["peritos"].find({"$or": [{"especialidad": None}, {"especialidad": ""}]}, {"_id": 1})
    ]
    if sin_especialidad:
        raise MigracionDetenida(f"Peritos sin especialidad (RF-13): {', '.join(sin_especialidad)}")

    cambios = [
        ("peritos", {"ultima_asignacion_en": {"$exists": False}}, {"ultima_asignacion_en": None}),
        (
            "configuracion",
            {"_id": "parametros_sismo", "emparejamiento": {"$exists": False}},
            {"emparejamiento": CONFIGURACION["emparejamiento"]},
        ),
        (
            "permisos",
            {"rol": "ADMINISTRADOR_GENERAL", "modulo": "asignacion_peritos", "actualizar": True},
            {"actualizar": False},
        ),
    ]
    cambios += [
        ("modulos", {"_id": modulo, "modulo_ers": {"$ne": ers}}, {"modulo_ers": ers})
        for modulo, (_, ers) in MODULOS.items()
    ]
    for coleccion, filtro, nuevo in cambios:
        n = db[coleccion].count_documents(filtro)
        if n:
            print(f"--  {coleccion}: {n} documentos con {sorted(nuevo)}")
        if aplicar and n:
            db[coleccion].update_many(filtro, {"$set": nuevo})
    if aplicar:
        exigir_que_cumplan(db, ["peritos", "modulos", "configuracion"])
    for coleccion in ("peritos", "modulos", "configuracion"):
        aplicar_validador(db, coleccion, aplicar)


if __name__ == "__main__":
    ejecutar("0008_peritos_modulos_configuracion", migrar)
