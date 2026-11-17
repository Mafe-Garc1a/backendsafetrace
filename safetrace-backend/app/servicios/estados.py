"""Servicios del Módulo G · Estados del inmueble (RF-38 a RF-47). Dueño: Valeria.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Pedir transición (inmueble, estado esperado, estado nuevo, causa);
consultar estado e historial. Es el único que cambia el estado de un inmueble (AD-06).

Puede llamar a los servicios de (matriz 5.2): auditoria (Aud).

Datos propios: app/crud/estados.py.

Pendiente: las reglas siguen en app/crud/estados.py; Valeria las trae aquí sin cambiar el comportamiento y mueve
las pruebas del módulo a tests/unit/.
"""
