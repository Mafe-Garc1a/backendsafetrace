"""Servicios del Módulo I · Enlace público (RF-59 a RF-61). Dueño: Jeferson.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Generar o revocar enlace; entregar la vista pública filtrada.

Puede llamar a los servicios de (matriz 5.2): cuentas (A), inmuebles (C), bitacora (D), inspecciones (H),
auditoria (Aud).

Datos propios: app/crud/enlaces.py.

Pendiente: las reglas siguen en app/crud/enlaces.py; Jeferson las trae aquí sin cambiar el comportamiento y
mueve las pruebas del módulo a tests/unit/.
"""
