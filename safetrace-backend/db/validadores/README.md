# Validadores `$jsonSchema` (Diseño DataBase v3, sección 12.1)

Un archivo JSON por colección: las 24 de la v3, incluida `recuperaciones_contrasena` (RF-73).
`db.validadores.cargar("inmuebles")` devuelve el validador listo para `collMod`.

- Revisar sin cambiar nada: `python -m db.validacion --revisar` (cuenta los documentos que no cumplen).
- Aplicar: `python -m db.migraciones.0002_crear_validadores` (se detiene si `--revisar` encuentra alguno).
- Modo final: `validationLevel: "strict"` y `validationAction: "error"`.
- No llevan `additionalProperties: false` en la raíz: los documentos con `schema_version` 2 traen campos que la
  v3 ya no escribe (por ejemplo `cambio_estado_aplicado`) y el código lee las dos versiones (sección 14.3).
  `tareas.datos` sí lo lleva: solo identificadores, nunca datos personales (RNF-20).
- Regla de orden (sección 14.2): si el código empieza a escribir algo nuevo, primero se migra el validador.
- `tests/test_validadores.py` comprueba que todo lo que escribe la API cumple estos validadores
  (mongomock no los aplica, así que se revisan en Python con `db.validacion.errores`).
