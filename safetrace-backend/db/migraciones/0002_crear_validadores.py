"""0002 · Validadores estrictos en las colecciones cuya forma no cambia con la v3 (Diseño DataBase v3, 12.1 y 14.1).

Dueño: Nicolás (BD). Se detiene si `python -m db.validacion --revisar` encuentra documentos que no cumplen
(por ejemplo, los datos de prueba del sismo de magnitud 10 a 800 km: sección 13.3).
Las colecciones que cambian de forma reciben su validador en su propia migración (0004 a 0009).
"""

from db.migraciones import aplicar_validador, ejecutar, exigir_que_cumplan

COLECCIONES = [
    "usuarios",
    "sesiones",
    "solicitudes_supresion",
    "roles",
    "permisos",
    "inmuebles",
    "zonas",
    "evidencias",
    "sismos",
    "historial_estados",
    "enlaces_publicos",
    "analisis_ia",
    "indices_priorizacion",
    "tareas",
    "auditoria",
]


def migrar(db, aplicar: bool) -> None:
    exigir_que_cumplan(db, COLECCIONES)
    for coleccion in COLECCIONES:
        aplicar_validador(db, coleccion, aplicar)


if __name__ == "__main__":
    ejecutar("0002_crear_validadores", migrar)
