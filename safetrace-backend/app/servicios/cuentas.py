"""Servicios del Módulo A · Cuentas y administración (RF-01 a RF-12, RF-73, RF-74). Dueño: Jeferson.

Capa de reglas del negocio (Estructura del backend v2, sección 2). Aquí van las reglas del módulo y las
operaciones que ofrece a los demás; el router llama a este archivo y este archivo llama a su crud.

Ofrece (Arquitectura v2, tabla 5.1): Usuario actual, rol y permisos; consultar la configuración (magnitud
mínima, radio, emparejamiento y parámetros del índice).

Puede llamar a los servicios de (matriz 5.2): notificaciones (K), auditoria (Aud).

Datos propios: app/crud/usuarios.py, app/crud/roles.py, app/crud/modulos.py, app/crud/permisos.py,
app/crud/modulo_permisos.py, app/crud/configuracion.py.

Pendiente: las reglas siguen en app/crud/usuarios.py, app/crud/roles.py, app/crud/modulos.py,
app/crud/permisos.py, app/crud/modulo_permisos.py, app/crud/configuracion.py; Jeferson las trae aquí sin cambiar
el comportamiento y mueve las pruebas del módulo a tests/unit/.
"""
