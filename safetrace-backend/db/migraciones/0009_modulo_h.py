"""0009 · solicitudes_inspeccion e inspecciones con los validadores de la sección 9 (RF-48 a RF-58, RF-72).

Dueño: Juan Miguel (H). Se aplica cuando el módulo H esté en main. Hoy las dos colecciones están vacías
en Atlas; si hubiera documentos con los estados viejos (SOLICITADA, FIRMADA, CANCELADA), la migración
se detiene: no se convierten a mano porque cambian reglas, no solo nombres.
"""

from db import indices
from db.migraciones import aplicar_validador, ejecutar, exigir_que_cumplan

COLECCIONES = ["solicitudes_inspeccion", "inspecciones"]


def migrar(db, aplicar: bool) -> None:
    for coleccion in COLECCIONES:
        print(f"--  {coleccion}: {db[coleccion].count_documents({})} documentos")
    exigir_que_cumplan(db, COLECCIONES)
    for coleccion in COLECCIONES:
        aplicar_validador(db, coleccion, aplicar)
        if aplicar:
            for claves, opciones in indices.INDICES[coleccion]:
                db[coleccion].create_index(claves, **opciones)


if __name__ == "__main__":
    ejecutar("0009_modulo_h", migrar)
