"""Validadores `$jsonSchema` del Diseño DataBase v3: un archivo JSON por colección (24).

Se aplican con migraciones (`db/migraciones/0002_crear_validadores.py` y siguientes), nunca desde la API.
Modo final: validationLevel "strict" y validationAction "error" (sección 12.1).
"""

import json
from pathlib import Path

CARPETA = Path(__file__).parent
COLECCIONES = tuple(sorted(p.stem for p in CARPETA.glob("*.json")))


def cargar(coleccion: str) -> dict:
    """El validador de la colección, listo para `collMod` o para `create_collection(validator=...)`."""
    return json.loads((CARPETA / f"{coleccion}.json").read_text(encoding="utf-8"))
