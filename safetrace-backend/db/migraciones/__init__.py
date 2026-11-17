"""Migraciones numeradas del Diseño DataBase v3 (sección 14; RNF-22).

Cada una se ejecuta sola, con el usuario administrador de Atlas y desde el computador de quien la corre
(nunca desde la API ni n8n):

    python -m db.migraciones.0001_quitar_borrar_en_historial            muestra qué cambiaría (no escribe)
    python -m db.migraciones.0001_quitar_borrar_en_historial --aplicar  aplica el cambio

Todas se pueden repetir: si el cambio ya está aplicado, no hacen nada. Antes de la primera, cambie las
credenciales que circularon (Atlas, JWT_SECRET, n8n) y pruebe en safetrace_test (MONGO_DB en el .env).
"""

import sys
from collections.abc import Callable

from pymongo.database import Database

from db import validadores
from db.validacion import revisar


class MigracionDetenida(Exception):
    """La migración encontró datos que debe corregir una persona antes de seguir."""


def aplicar_validador(db: Database, coleccion: str, aplicar: bool) -> None:
    """Crea la colección con su validador o se lo cambia con collMod (modo strict y error, sección 12.1)."""
    validador = validadores.cargar(coleccion)
    if not aplicar:
        print(f"--  {coleccion}: se aplicaría su validador")
        return
    if coleccion in db.list_collection_names():
        db.command("collMod", coleccion, validator=validador, validationLevel="strict", validationAction="error")
    else:
        db.create_collection(coleccion, validator=validador, validationLevel="strict", validationAction="error")
    print(f"ok  {coleccion}: validador aplicado")


def exigir_que_cumplan(db: Database, colecciones: list[str]) -> None:
    """Se detiene si algún documento no cumple el validador (lo mismo que `python -m db.validacion --revisar`)."""
    conteo = {c: n for c, n in revisar(db).items() if c in colecciones and n}
    if conteo:
        detalle = ", ".join(f"{c}: {n}" for c, n in conteo.items())
        raise MigracionDetenida(f"Hay documentos que no cumplen el validador ({detalle}). Corríjalos y repita.")


def ejecutar(nombre: str, migracion: Callable[[Database, bool], None]) -> None:
    """Punto de entrada común: sin --aplicar solo muestra lo que haría."""
    from core.database import obtener_db

    aplicar = "--aplicar" in sys.argv
    db = obtener_db()
    print(f"== {nombre} en la base {db.name} ({'aplicando' if aplicar else 'simulación: agregue --aplicar'})")
    try:
        migracion(db, aplicar)
    except MigracionDetenida as e:
        print(f"!!  {e}")
        sys.exit(1)
