"""Servicios del Módulo E · Revisión del propietario (RF-28 a RF-30). Dueño: Nicolás.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Registrar revisión; consultar la fecha de la última revisión.

Puede llamar a los servicios de (matriz 5.2): cuentas (A), inmuebles (C), bitacora (D), estados (G),
notificaciones (K), auditoria (Aud). Por medio de una tarea en la cola, sin llamada directa: ia_indice (J).

Datos propios: app/crud/revisiones.py.

Pendiente: las reglas siguen en app/crud/revisiones.py; Nicolás las trae aquí sin cambiar el comportamiento y
mueve las pruebas del módulo a tests/unit/.
"""
