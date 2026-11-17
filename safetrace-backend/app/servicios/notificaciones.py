"""Servicios del Módulo K · Notificaciones y procesos (RF-69 a RF-71, RF-75). Dueño: Mafe.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Enviar correo; crear notificación dentro de la aplicación; consultar y
marcar leídas; registrar y consultar tareas.

Puede llamar a los servicios de (matriz 5.2): auditoria (Aud).

Datos propios: app/crud/notificaciones.py.

Pendiente: las reglas siguen en app/crud/notificaciones.py; Mafe las trae aquí sin cambiar el comportamiento y
mueve las pruebas del módulo a tests/unit/.
"""
