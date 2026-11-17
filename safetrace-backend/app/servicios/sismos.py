"""Servicios del Módulo F · Sismos (RF-31 a RF-37). Dueño: Nicolás.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Recibir un sismo (desde n8n); consultar un sismo.

Puede llamar a los servicios de (matriz 5.2): cuentas (A), inmuebles (C), estados (G), notificaciones (K),
auditoria (Aud). Por medio de una tarea en la cola, sin llamada directa: ia_indice (J).

Datos propios: app/crud/sismos.py.

Pendiente: las reglas siguen en app/crud/sismos.py; Nicolás las trae aquí sin cambiar el comportamiento y mueve
las pruebas del módulo a tests/unit/.
"""
