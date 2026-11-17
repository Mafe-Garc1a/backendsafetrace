"""0005 · notificaciones: tipo SOLICITUD_ASIGNADA, `canales` y `leida_en` (RF-49, RF-75; Diseño DataBase v3, 10.4).

Dueña: Mafe (K). Va ANTES de desplegar el código que escribe el tipo nuevo (regla de orden, 14.2).
Las notificaciones anteriores solo salieron por correo: reciben canales ["CORREO"]. No se inventa `leida_en`:
sin el campo, el centro de notificaciones las muestra como no leídas.
"""

from db.migraciones import aplicar_validador, ejecutar, exigir_que_cumplan


def migrar(db, aplicar: bool) -> None:
    sin_canales = {"canales": {"$exists": False}}
    print(f"--  notificaciones sin canales: {db['notificaciones'].count_documents(sin_canales)}")
    if aplicar:
        r = db["notificaciones"].update_many(sin_canales, {"$set": {"canales": ["CORREO"]}})
        print(f"ok  {r.modified_count} notificaciones con canales ['CORREO']")
        exigir_que_cumplan(db, ["notificaciones"])
    aplicar_validador(db, "notificaciones", aplicar)


if __name__ == "__main__":
    ejecutar("0005_notificaciones", migrar)
