"""0001 · Nadie tiene `borrar` en los 7 módulos de historial, ni siquiera el SUPERADMIN (Diseño DataBase v3, 6.8, C-02).

Dueño: Nicolás (BD). No rompe ningún validador. Después, el código lo impone con MODULOS_SOLO_AGREGAR.
"""

from app.crud.modulo_permisos import MODULOS_SOLO_AGREGAR
from db.migraciones import ejecutar


def migrar(db, aplicar: bool) -> None:
    filtro = {"modulo": {"$in": sorted(MODULOS_SOLO_AGREGAR)}, "borrar": True}
    print(f"--  permisos con borrar en historial: {db['permisos'].count_documents(filtro)}")
    if aplicar:
        r = db["permisos"].update_many(filtro, {"$set": {"borrar": False}})
        print(f"ok  {r.modified_count} permisos sin borrar")


if __name__ == "__main__":
    ejecutar("0001_quitar_borrar_en_historial", migrar)
