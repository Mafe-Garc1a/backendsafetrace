"""0003 · Índices de la v3: crea los 10 nuevos y quita los que ya no sirven (Diseño DataBase v3, 11.1 y 11.2).

Dueño: Nicolás (BD). Los dos únicos parciales (11.3) no van aquí: se crean con
`python -m db.indices --con-parciales` cuando una prueba contra safetrace_test confirme que funcionan.
"""

from db import indices
from db.migraciones import ejecutar

# (colección, claves) de los índices que se quitan
QUITAR = [
    ("inspecciones", [("inmueble_id", 1), ("es_version_activa", 1)]),  # el campo deja de existir
    ("inspecciones", [("constancia.estado", 1), ("constancia.vigente_hasta", 1)]),  # el campo deja de existir
    ("peritos", [("estado_credencial", 1)]),  # lo cubre {estado_credencial, ultima_asignacion_en}
    ("solicitudes_inspeccion", [("perito_id", 1), ("estado", 1)]),  # código anterior; lo cubre {estado, perito_id}
    ("solicitudes_inspeccion", [("estado", 1)]),  # código anterior; lo cubre {estado, creado_en}
]


def migrar(db, aplicar: bool) -> None:
    for coleccion, claves in QUITAR:
        existentes = {tuple(i["key"].items()): i["name"] for i in db[coleccion].list_indexes()}
        nombre = existentes.get(tuple(claves))
        if nombre is None:
            continue
        print(f"--  {coleccion}: se quita {nombre}")
        if aplicar:
            db[coleccion].drop_index(nombre)
    if aplicar:
        indices.crear(db)
    else:
        print("--  se crearían los índices de db/indices.py (si ya existen, no cambia nada)")


if __name__ == "__main__":
    ejecutar("0003_indices", migrar)
