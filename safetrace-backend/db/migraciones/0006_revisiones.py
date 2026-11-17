"""0006 · revisiones deja de exigir `cambio_estado_aplicado` (Diseño DataBase v3, 8.3).

Dueño: Nicolás (E). Va ANTES del código que deja de escribirlo. Las revisiones v2 lo conservan y no molesta:
la API lo calcula desde historial_estados para las nuevas.
"""

from db.migraciones import aplicar_validador, ejecutar, exigir_que_cumplan


def migrar(db, aplicar: bool) -> None:
    exigir_que_cumplan(db, ["revisiones"])
    aplicar_validador(db, "revisiones", aplicar)


if __name__ == "__main__":
    ejecutar("0006_revisiones", migrar)
