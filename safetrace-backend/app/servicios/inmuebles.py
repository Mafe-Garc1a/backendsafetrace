"""Servicios del Módulo C · Inmuebles (RF-17 a RF-21). Dueño: Valeria.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Consultar el inmueble y su dueño; buscar inmuebles dentro de un radio;
catálogo de zonas.

Puede llamar a los servicios de (matriz 5.2): cuentas (A), auditoria (Aud).

Datos propios: app/crud/inmuebles.py.

Pendiente: las reglas siguen en app/crud/inmuebles.py; Valeria las trae aquí sin cambiar el comportamiento y
mueve las pruebas del módulo a tests/unit/.
"""
