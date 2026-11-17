"""Servicios del Módulo B · Peritos (RF-13 a RF-16). Dueño: Brayan.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Saber si un perito está habilitado; listar peritos validados con su número
de solicitudes «Asignada» y su última asignación.

Puede llamar a los servicios de (matriz 5.2): cuentas (A), notificaciones (K), auditoria (Aud).

Datos propios: app/crud/peritos.py.

Pendiente: las reglas siguen en app/crud/peritos.py; Brayan las trae aquí sin cambiar el comportamiento y mueve
las pruebas del módulo a tests/unit/.
"""
