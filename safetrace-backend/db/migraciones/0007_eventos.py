"""0007 · eventos: `estado`, `reemplazado_por` e `invalidacion` (Diseño DataBase v3, 8.1).

Dueña: Mafe (D). Campos nuevos y opcionales para los documentos v2: un evento sin `estado` se lee como VIGENTE
(sección 14.3), así que no se reescriben en masa. Va DESPUÉS del código.
"""

from db.migraciones import aplicar_validador, ejecutar, exigir_que_cumplan


def migrar(db, aplicar: bool) -> None:
    sin_estado = db["eventos"].count_documents({"estado": {"$exists": False}})
    print(f"--  eventos v2 sin estado (se leen como VIGENTE): {sin_estado}")
    exigir_que_cumplan(db, ["eventos"])
    aplicar_validador(db, "eventos", aplicar)


if __name__ == "__main__":
    ejecutar("0007_eventos", migrar)
