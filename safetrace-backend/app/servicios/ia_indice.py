"""Servicios del Módulo J · IA e índice de priorización (RF-62 a RF-68). Dueño: Brayan.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Comparar fotos; calcular índice; consultar análisis e índice (las gráficas,
solo perito y administrador).

Puede llamar a los servicios de (matriz 5.2): cuentas (A), inmuebles (C), bitacora (D), revisiones (E), sismos
(F), auditoria (Aud).

Datos propios: app/crud/ia_indice.py.

Pendiente: las reglas siguen en app/crud/ia_indice.py; Brayan las trae aquí sin cambiar el comportamiento y
mueve las pruebas del módulo a tests/unit/.
"""
