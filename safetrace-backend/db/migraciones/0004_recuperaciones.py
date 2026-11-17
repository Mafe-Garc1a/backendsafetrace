"""0004 · Colección nueva recuperaciones_contrasena con su validador e índices (RF-73; Diseño DataBase v3, 6.3).

Dueño: Jeferson (A). La colección está vacía: no toca datos.
"""

from db import indices
from db.migraciones import aplicar_validador, ejecutar

COLECCION = "recuperaciones_contrasena"


def migrar(db, aplicar: bool) -> None:
    aplicar_validador(db, COLECCION, aplicar)
    if aplicar:
        for claves, opciones in indices.INDICES[COLECCION]:
            db[COLECCION].create_index(claves, **opciones)
        print(f"ok  {COLECCION}: {len(indices.INDICES[COLECCION])} índices")


if __name__ == "__main__":
    ejecutar("0004_recuperaciones", migrar)
