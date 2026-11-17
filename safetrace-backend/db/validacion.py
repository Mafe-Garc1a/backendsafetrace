"""Revisión de documentos contra los validadores del Diseño DataBase v3 (sección 12.1).

    python -m db.validacion --revisar      cuenta, en el servidor, los documentos que no cumplen (no cambia nada)

`errores(documento, esquema)` hace la misma revisión en Python: la usan las pruebas, porque mongomock no aplica
validadores. Cubre lo que usan los archivos de db/validadores: bsonType, required, properties,
additionalProperties, enum, minimum, maximum, exclusiveMinimum, minLength, maxLength, pattern, items,
minItems, maxItems y anyOf.
"""

import re
import sys
from datetime import datetime
from decimal import Decimal

from bson import Decimal128, ObjectId

from db import validadores

TIPOS = {
    "objectId": lambda v: isinstance(v, ObjectId),
    "date": lambda v: isinstance(v, datetime),
    "string": lambda v: isinstance(v, str),
    "bool": lambda v: isinstance(v, bool),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "long": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "double": lambda v: isinstance(v, float),
    "decimal": lambda v: isinstance(v, (Decimal, Decimal128)),
    "null": lambda v: v is None,
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}


def errores(valor, esquema: dict, ruta: str = "$") -> list[str]:
    """Lista de incumplimientos de `valor` frente a `esquema` (vacía si cumple)."""
    if "$jsonSchema" in esquema:
        esquema = esquema["$jsonSchema"]
    fallos: list[str] = []
    tipos = esquema.get("bsonType")
    if tipos is not None:
        tipos = tipos if isinstance(tipos, list) else [tipos]
        if not any(TIPOS[t](valor) for t in tipos):
            return [f"{ruta}: se esperaba {tipos}, llegó {type(valor).__name__}"]
    if "enum" in esquema and valor not in esquema["enum"]:
        fallos.append(f"{ruta}: {valor!r} no está en {esquema['enum']}")
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if "minimum" in esquema:
            if esquema.get("exclusiveMinimum") and valor <= esquema["minimum"]:
                fallos.append(f"{ruta}: {valor} debe ser mayor que {esquema['minimum']}")
            elif valor < esquema["minimum"]:
                fallos.append(f"{ruta}: {valor} es menor que {esquema['minimum']}")
        if "maximum" in esquema and valor > esquema["maximum"]:
            fallos.append(f"{ruta}: {valor} es mayor que {esquema['maximum']}")
    if isinstance(valor, str):
        if len(valor) < esquema.get("minLength", 0):
            fallos.append(f"{ruta}: texto más corto que {esquema['minLength']}")
        if "maxLength" in esquema and len(valor) > esquema["maxLength"]:
            fallos.append(f"{ruta}: texto más largo que {esquema['maxLength']}")
        if "pattern" in esquema and not re.search(esquema["pattern"], valor):
            fallos.append(f"{ruta}: {valor!r} no cumple {esquema['pattern']}")
    if isinstance(valor, list):
        if len(valor) < esquema.get("minItems", 0):
            fallos.append(f"{ruta}: menos de {esquema['minItems']} elementos")
        if "maxItems" in esquema and len(valor) > esquema["maxItems"]:
            fallos.append(f"{ruta}: más de {esquema['maxItems']} elementos")
        if "items" in esquema:
            for i, elemento in enumerate(valor):
                fallos += errores(elemento, esquema["items"], f"{ruta}[{i}]")
    if isinstance(valor, dict):
        for campo in esquema.get("required", []):
            if campo not in valor:
                fallos.append(f"{ruta}: falta {campo}")
        propiedades = esquema.get("properties", {})
        for campo, sub in propiedades.items():
            if campo in valor:
                fallos += errores(valor[campo], sub, f"{ruta}.{campo}")
        if esquema.get("additionalProperties") is False:
            sobrantes = set(valor) - set(propiedades)
            if sobrantes:
                fallos.append(f"{ruta}: campos no permitidos {sorted(sobrantes)}")
    if "anyOf" in esquema and not any(not errores(valor, opcion, ruta) for opcion in esquema["anyOf"]):
        fallos.append(f"{ruta}: no cumple ninguna de las opciones de anyOf")
    return fallos


def revisar(db=None) -> dict[str, int]:
    """Cuenta en el servidor, por colección, los documentos que el validador rechazaría. No cambia nada."""
    from core.database import obtener_db

    db = db if db is not None else obtener_db()
    resultado = {}
    for coleccion in validadores.COLECCIONES:
        resultado[coleccion] = db[coleccion].count_documents({"$nor": [validadores.cargar(coleccion)]})
    return resultado


if __name__ == "__main__":
    if "--revisar" not in sys.argv:
        print("Uso: python -m db.validacion --revisar")
        sys.exit(2)
    conteo = revisar()
    for coleccion, n in conteo.items():
        print(f"{'ok' if n == 0 else '!!'}  {coleccion}: {n} documentos no cumplen")
    sys.exit(1 if any(conteo.values()) else 0)
