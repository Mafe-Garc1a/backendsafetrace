# SafeTrace · Backend

API en **Python + FastAPI**, **MongoDB** y **Redis**, con los 11 módulos de la **ERS v2.1** (A a K, RF-01 a RF-75),
las 24 colecciones del *Diseño DataBase v3* y la *Integración Redis v2*. Sigue la misma organización que el backend de **avisena**: `main.py` y `core/`
en la raíz, y dentro de `app/` una carpeta por capa (`router`, `servicios`, `crud`, `schemas`) con un archivo
por módulo.

No usa Docker: se ejecuta con un entorno virtual de Python y una base MongoDB (Atlas o instalada en el equipo).

La visión general del proyecto (módulos, flujo, roles, reglas del equipo y equipo) está en
[`docs/PROYECTO.md`](docs/PROYECTO.md).

## Cómo arrancar (Windows, VS Code)

1. Crear el entorno virtual e instalar dependencias (en la raíz del repositorio):
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements-dev.txt
   copy .env.example .env
   ```
2. Tener una base MongoDB y poner su dirección en `MONGO_URI` del `.env` (ver la sección siguiente).
   Redis es opcional en el equipo: con `REDIS_URL` vacío la API funciona solo con Mongo (sin caché ni límites).
   En el despliegue, `REDIS_URL` va solo en las variables del proveedor, nunca en el repositorio.
3. Completar en `.env` `JWT_SECRET`, `CREDENCIAL_SERVICIO_N8N`, `SUPERADMIN_CORREO`, `SUPERADMIN_CONTRASENA`,
   `ADMIN_CORREO` y `ADMIN_CONTRASENA`.
4. Crear índices y datos iniciales (configuración, zonas, roles, módulos, permisos, el superadministrador y el
   primer administrador general). **Repetirlo después de cada actualización** que agregue módulos o permisos:
   ```powershell
   python -m core.database      # ¿Conexión exitosa?: True
   python -m db.indices
   python -m db.semillas
   python -m db.validacion --revisar   # cuenta los documentos que los validadores rechazarían
   ```
   En una base que ya tenía datos de la v2, antes de esto se ejecutan las migraciones 0001 a 0009 en el orden de
   [`db/migraciones/README.md`](db/migraciones/README.md), primero contra `safetrace_test`.
5. Levantar la API: pestaña **Ejecutar y depurar** → **API (uvicorn)**, o `uvicorn main:app --reload`.
   Abrir http://localhost:8000/docs; el botón **Authorize** inicia sesión (en *username* va el correo).
6. Levantar el trabajador (correos y comparación de fotos) en otra terminal: `python -m trabajador.main`.
7. Pruebas: pestaña **Testing** de VS Code, o `pytest`. No necesitan MongoDB ni Redis (usan mongomock y
   fakeredis). Al terminar cada prueba se revisa que todo lo escrito cumpla los validadores de `db/validadores/`.
8. Antes de abrir un pull request, ejecutar lo mismo que la CI:
   ```powershell
   ruff check .; ruff format --check .; lint-imports; pytest; pip-audit -r requirements.txt
   ```

## Base de datos sin Docker

| Opción | Cuándo | `MONGO_URI` |
|---|---|---|
| **MongoDB Atlas** (capa gratuita M0) — recomendada | Equipo y despliegue. Es un conjunto de réplicas, así que tiene transacciones (sección 7.2 del diseño). | `mongodb+srv://USUARIO:CONTRASENA@CLUSTER.mongodb.net/?retryWrites=true&w=majority` |
| **MongoDB Community** instalado en Windows | Trabajo sin internet. | `mongodb://localhost:27017` |

**Atlas:** crear el clúster M0, un usuario de base de datos (*Database Access*) y permitir la IP del equipo
(*Network Access*). Copiar la cadena de *Connect → Drivers* en `MONGO_URI`.

**Local:** instalar [MongoDB Community Server](https://www.mongodb.com/try/download/community) como servicio
de Windows (opcionalmente con MongoDB Compass). Funciona sin más configuración: sin conjunto de réplicas,
`crud/estados.py` hace el cambio de estado sin transacción y lo sigue protegiendo con `estado.version`.
Para tener transacciones también en local, convertirlo en conjunto de réplicas de un nodo:

1. En `C:\Program Files\MongoDB\Server\<versión>\bin\mongod.cfg` agregar:
   ```yaml
   replication:
     replSetName: rs0
   ```
2. Reiniciar el servicio (`net stop MongoDB` y `net start MongoDB` en una terminal de administrador).
3. En `mongosh`: `rs.initiate()`.
4. Usar `MONGO_URI=mongodb://localhost:27017/?replicaSet=rs0`.

## Estructura

```
safetrace/
├── main.py                      # crea FastAPI, CORS, manejadores de error y registra los routers
├── core/                        # lo compartido por toda la API
│   ├── config.py                #   variables de entorno (.env) → `settings`
│   ├── database.py              #   cliente de MongoDB, `get_db`, ids y serialización
│   ├── security.py              #   bcrypt y tokens JWT (RNF-09, RNF-11)
│   ├── fechas.py                #   UTC con milisegundos, suma de meses
│   ├── email.py                 #   correo transaccional (sin proveedor: se simula)
│   ├── almacenamiento.py        #   proveedor de archivos compatible con S3 (R2, S3 o MinIO)
│   ├── paginacion.py            #   máximo 50 por página (RNF-30)
│   ├── redis_cliente.py         #   cliente de Redis y `tolerante` (si Redis falla, se sigue con Mongo)
│   ├── cache.py                 #   sesiones y permisos en Redis (Integración Redis v2)
│   ├── limite.py                #   límites de inicio de sesión, enlace público, verificación y recuperación
│   ├── errores.py               #   ErrorNegocio, formato único de error y catálogo de códigos
│   ├── correlacion.py           #   X-Request-ID en respuestas, logs y tareas
│   ├── circuito.py              #   circuit breaker por proveedor externo
│   ├── modelos_indice.py        #   fórmulas del índice de priorización (ADR 0014)
│   └── registro.py              #   logs sin datos personales (RNF-20)
├── app/
│   ├── router/                  # capa de entrada: endpoints de FastAPI
│   │   ├── dependencies.py      #   usuario actual, requiere_permiso, credencial de n8n y acceso al inmueble
│   │   ├── comunes.py           #   validar_zona y url_archivo, compartidas por D, E y B
│   │   ├── salud.py             #   GET / y GET /salud
│   │   ├── auth.py              #   A · registro, sesión y recuperación      RF-01 a RF-03, RF-07, RF-73
│   │   ├── usuarios.py          #   A · usuarios, supresión y administradores RF-04 a RF-06, RF-08, RF-09, RF-74
│   │   ├── auditoria.py         #   A · consulta de auditoría                RF-10
│   │   ├── configuracion.py     #   A · magnitud mínima y radio              RF-11, RF-12
│   │   ├── roles.py             #   roles (como en avisena)
│   │   ├── modulos.py           #   módulos (como en avisena)
│   │   ├── permisos.py          #   permisos por rol y módulo (como en avisena)
│   │   ├── peritos.py           #   B · Peritos                    RF-13 a RF-16
│   │   ├── inmuebles.py         #   C · Inmuebles y zonas          RF-17 a RF-21, RF-23
│   │   ├── bitacora.py          #   D · Bitácora y evidencias      RF-22 a RF-27
│   │   ├── revisiones.py        #   E · Revisión del propietario   RF-28 a RF-30
│   │   ├── sismos.py            #   F · Sismos                     RF-31 a RF-37
│   │   ├── estados.py           #   G · Estados del inmueble       RF-38 a RF-47
│   │   ├── inspecciones.py      #   H · Inspecciones y constancias RF-48 a RF-58, RF-72
│   │   ├── enlaces.py           #   I · Enlace público             RF-59 a RF-61
│   │   ├── ia_indice.py         #   J · IA e índice                RF-62 a RF-68
│   │   └── notificaciones.py    #   K · Notificaciones y procesos  RF-69 a RF-71, RF-75
│   ├── servicios/               # reglas del negocio por módulo (H ya las tiene aquí; el resto, en transición, ADR 0017)
│   ├── crud/                    # acceso a MongoDB y, por ahora, reglas de negocio (mismos nombres)
│   │   ├── permisos.py          #   verificar_permisos (como verify_permissions de avisena)
│   │   └── modulo_permisos.py   #   CRUD de la colección permisos
│   └── schemas/                 # modelos Pydantic Base / Create / Update / Out (mismos nombres)
├── trabajador/                  # proceso aparte que ejecuta la colección `tareas`
├── db/
│   ├── indices.py               # crea los índices del Diseño DataBase v3 (--con-parciales: los de 11.3)
│   ├── semillas.py              # configuración, zonas, roles, módulos, permisos y usuarios iniciales
│   ├── validadores/             # $jsonSchema de las 24 colecciones (sección 12.1)
│   ├── validacion.py            # --revisar: documentos que los validadores rechazarían
│   └── migraciones/             # 0001 a 0009: de la v2 a la v3 (RNF-22), con dueño cada una
├── n8n/                         # flujos exportados (sismos y tareas diarias)
├── modelos_ia/                  # pesos del modelo entrenado en Colab (no van a git)
├── tests/                       # pruebas con mongomock (sin MongoDB)
├── http/ejemplos.http           # peticiones de prueba (extensión REST Client)
├── docs/                        # manual de mantenimiento y decisiones técnicas (docs/decisiones/, ADR)
├── .vscode/                     # intérprete, depuración y extensiones
├── .github/workflows/ci.yml     # integración continua (RNF-32)
├── .github/dependabot.yml       # actualizaciones semanales de dependencias (ADR 0016)
├── Procfile                     # despliegue: web (uvicorn) y worker (trabajador)
└── requirements.txt / requirements-dev.txt / pyproject.toml / .env.example
```

### Las capas (como en avisena, más servicios)

| Carpeta | Qué va ahí |
|---|---|
| `app/router/` | Endpoints. Cada archivo declara su `modulo` (como en avisena). Reciben `db: Database = Depends(get_db)` y el usuario con `Depends(requiere_permiso(modulo, "insertar"))` (o `actualizar`, `seleccionar`, `borrar`) o `Depends(get_current_user)`, validan con `app.schemas` y llaman a `app.servicios` o, mientras dura la transición, a `app.crud`. |
| `app/schemas/` | Modelos Pydantic de lo que entra y sale (`Base` / `Create` / `Update` / `Out` y `Page` para listas paginadas). |
| `app/servicios/` | Reglas del negocio de cada módulo y lo que ofrece a los demás. Cada archivo indica su dueño y a qué servicios puede llamar. `inspecciones.py` (H) ya tiene sus reglas aquí y sirve de ejemplo; en los demás, cada dueño trae las reglas desde su `crud` sin cambiar el comportamiento (ADR 0017). |
| `app/crud/` | Único lugar que habla con MongoDB; cada archivo solo escribe las colecciones de su módulo. Funciones síncronas que reciben `db` como primer parámetro. |

El sentido de las importaciones es `app.router` → `app.servicios` → `app.crud`, y `core` no importa nada de `app`
ni de `trabajador`. `lint-imports` lo comprueba en la CI con los contratos de `pyproject.toml`.

Diferencias con avisena, por lo que pide el diseño:

- **MongoDB en vez de MySQL:** `get_db` entrega la base de PyMongo; los ids son `ObjectId` y `serializar()` los devuelve como texto en `id`.
- **Sesiones con cierre por inactividad (RNF-11):** el token es un JWT como en avisena, pero además se guarda su hash en
  `sesiones` y en Redis; cada petición extiende la sesión 30 minutos (Redis en cada petición, Mongo cada 5 minutos)
  y cerrar sesión la borra de los dos (RF-03). Redis también guarda la caché de permisos y los límites por IP.
- **Permisos (igual que avisena):** colecciones `roles`, `modulos` y `permisos` (rol × módulo × insertar/actualizar/
  seleccionar/borrar), administrables desde `/admin/roles`, `/admin/modulos` y `/admin/permisos`. En vez de llamar a
  `verify_permissions` dentro de cada ruta, se usa la dependencia `requiere_permiso(modulo, accion)`, que hace lo mismo.
  Además, `obtener_inmueble_autorizado(...)` limita cada consulta a los inmuebles propios, asignados o (con el
  permiso `supervision_inmuebles`) a todos. Roles iniciales: `SUPERADMIN` (todo), `ADMINISTRADOR_GENERAL`, `PERITO`
  y `PROPIETARIO`.
- **Errores:** todos responden con el mismo formato (`detail`, `codigo`, `request_id`; el 422 agrega `errores`).
  Las reglas de negocio lanzan subclases de `ErrorNegocio` (`core/errores.py`) y `main.py` las traduce; los
  errores inesperados y los de base de datos responden un 500 genérico, sin filtrar detalles internos. El
  catálogo de códigos está en [`docs/MANUAL.md`](docs/MANUAL.md).

## Reglas del equipo

1. **Cada colección tiene un dueño.** Solo el archivo de `app/crud` de ese módulo la escribe; los demás
   llaman a sus funciones. En `inmuebles`, los campos calculados se escriben con funciones de `crud/inmuebles.py`:
   `estado` solo G, `ultimo_indice` solo J, `ultimos_eventos` solo D y `revision_semestral` solo E.
2. **Solo G cambia el estado**, con `crud.estados.pedir_transicion`. J (IA e índice) nunca la llama (RNF-37).
3. **Lo lento va a la cola:** `crud.notificaciones.encolar_tarea` / `notificar`, y lo ejecuta el trabajador.
4. **Nada de datos personales en logs, tareas ni auditoría** (RNF-20).
5. **Ramas y revisión:** una rama por tarjeta del tablero (`feat/b-validar-credenciales`),
   pull request revisado por otro integrante y CI en verde antes de unir a `main` (RNF-32). La CI ejecuta
   `ruff check`, `ruff format --check`, `lint-imports`, `pytest` y `pip-audit`.

## Pendiente (decisiones abiertas del diseño, sección 11.2)

| Qué | Dónde | Comportamiento actual |
|---|---|---|
| Pesos definitivos del índice de priorización | `configuracion` → `parametros_indice` | Se calcula con pesos provisionales (ADR 0014). Si el cálculo falla, el marcado por sismo sigue sin índice. |
| Modelo de comparación de fotos (Colab) | `crud/ia_indice.py` → `cargar_modelo`, `comparar` | El análisis queda PENDIENTE y la tarea falla tras 3 intentos (FALLIDO, se puede reintentar). |
| Proveedor de archivos | `core/almacenamiento.py` | Integrado y compatible con S3. Sin `PROVEEDOR_ARCHIVOS_URL`, `ARCHIVOS_BUCKET` y claves, la subida y la lectura responden 501. Falta crear el bucket de producción. |
| Proveedor de correo | `core/email.py` | Sin `CORREO_API_KEY` el envío se simula (se registra en el log). |
| Criterio para emparejar SGC y USGS | `configuracion.parametros_sismo.emparejamiento` | Propuesta: 120 s y ≤ 100 km, configurable; prevalece la magnitud del SGC. |
| Lista definitiva de zonas | `db/semillas.py` | Lista de ejemplo. |
| Aplicar validadores y migraciones en Atlas | `db/migraciones/` | Escritas y probadas con mongomock. Antes: cambiar las credenciales que circularon (Atlas, `JWT_SECRET`, n8n) y probar en `safetrace_test`. |
| Pruebas de integración | `tests/` | mongomock no ejecuta transacciones, validadores ni índices parciales: falta una corrida contra `safetrace_test`. |
| Decisiones del PO (Diseño DataBase v3, 11.2) | BD-03, BD-04, BD-05, BD-06, BD-09 | Implementadas como su propuesta; ver `CAMBIOS_backend_v2.md`. |
| Reglas en la capa de servicios | `app/servicios/` | Archivos creados con su dueño; las reglas siguen en `app/crud/` (ADR 0017). |
| Capa de dominio y repositorios; dividir `crud/inspecciones.py` | `app/crud/` | Después del MVP (ADR 0015). |
