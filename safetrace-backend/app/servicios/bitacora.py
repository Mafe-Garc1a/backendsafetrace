"""Servicios del Módulo D · Bitácora y evidencias (RF-22 a RF-27). Dueño: Mafe.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Registrar evento o evidencia; consultar antecedentes y línea cronológica.

Puede llamar a los servicios de (matriz 5.2): cuentas (A), inmuebles (C), auditoria (Aud).

Datos propios: app/crud/bitacora.py.

Pendiente: las reglas siguen en app/crud/bitacora.py; Mafe las trae aquí sin cambiar el comportamiento y mueve
las pruebas del módulo a tests/unit/.
"""
