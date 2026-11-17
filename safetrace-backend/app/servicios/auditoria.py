"""Servicios del Transversal · Auditoría (transversal) (RF-10, RNF-16, RNF-21). Dueño: Jeferson.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Registrar evento; consultar auditoría.

Puede llamar a los servicios de (matriz 5.2): ninguno.

Datos propios: app/crud/auditoria.py.

Pendiente: las reglas siguen en app/crud/auditoria.py; Jeferson las trae aquí sin cambiar el comportamiento y
mueve las pruebas del módulo a tests/unit/.
"""
