# SafeTrace · Backend v2: registro de cambios por módulo y dueño

**Fecha:** 17 de noviembre de 2026
**Base:** `backend_actualizado` de Jeferson (16 nov 2026): 104 pruebas, 88 % de cobertura.
**Referencias:** ERS v2.1 (75 RF), Diseño DataBase v3 (Nicolás, aprobado por la PO el 16 nov), Integración Redis v2,
Arquitectura backend v2 y Estructura backend v2 (Jeferson).
**Estado:** propuesta para que **cada dueño revise y suba su módulo**. Nada se ha aplicado en Atlas.

## Resultado de las verificaciones (17 nov)

| Verificación | Resultado |
|---|---|
| `pytest` | 158 pruebas pasan (la base tenía 104) |
| Cobertura `app` + `core` | 90,7 % (mínimo de la CI: 70 %) |
| `ruff check` / `ruff format --check` | Sin errores |
| `lint-imports` | 2 contratos cumplidos (capas `router → servicios → crud`; `core` no importa `app`) |
| `pip-audit -r requirements.txt` | Sin vulnerabilidades conocidas |
| Validadores | Al final de **cada** prueba se revisa que todo lo que escribió la API cumpla los 24 `$jsonSchema` |

## Antes de subir nada: seguridad

1. **Cambiar las credenciales que circularon en el zip de noviembre:** contraseña del usuario de Atlas,
   `JWT_SECRET`, `CREDENCIAL_SERVICIO_N8N` y la contraseña del superadmin. Hasta entonces no se ejecuta ninguna migración.
2. `.env`, el entorno virtual (`Lib/`, `Scripts/`, `venv/`) y `__pycache__` **no van** en el repositorio ni en zips.
   Esta copia no los trae; copie `.env.example` a `.env` y llénelo en su equipo.
3. `REDIS_URL` y la cadena de Atlas van solo en las variables del despliegue.

## Cómo subirlo (recomendado)

Los módulos dependen unos de otros (por ejemplo, H usa funciones nuevas de B y K, y las pruebas revisan todos los
validadores), así que la CI de `main` solo queda en verde cuando están todos. Propuesta:

1. Crear la rama compartida `integracion/backend-v2` desde `main`.
2. Cada dueño sube **sus archivos** (lista de abajo) en un commit propio a esa rama, en este orden:
   transversal y BD (Nicolás, Jeferson) → A e I (Jeferson) → K y D (Mafe) → B y J (Brayan) → C y G (Valeria) →
   E y F (Nicolás) → H (Juan Miguel).
3. Un solo pull request a `main`, revisado por las parejas cruzadas de la Distribución de módulos v2
   (H↔C/G, E/F↔B/J, A/I↔D/K), con la CI en verde.

---

## Transversal (infraestructura, CI y documentación)

**Dueños:** Nicolás (infraestructura y Redis, fases 1-2), Jeferson (DevOps, CI).

| Archivo | Cambio |
|---|---|
| `core/redis_cliente.py` (nuevo) | Cliente de Redis y `tolerante`: si Redis falla, se pausa 15 s y todo sigue con Mongo (Redis v2 §8). |
| `core/database.py` | `en_transaccion(db, operacion)`: transacción si hay réplica (Atlas), sin ella en local. |
| `core/config.py`, `.env.example` | Variables de Redis, límites, `URL_FRONTEND`, `MINUTOS_RECUPERACION`, `RECUPERACIONES_MAX_POR_HORA`, `SESION_RENOVAR_MONGO_SEGUNDOS`. |
| `core/errores.py` | Código `DEMASIADAS_PETICIONES` para el 429. |
| `.github/workflows/ci.yml` (restaurado en la raíz) | ruff, lint-imports, pytest con cobertura ≥ 70 % y pip-audit en cada pull request (RNF-32). |
| `.gitignore` | Restaurado: el del venv (`*`) había reemplazado al del proyecto. |
| `.gitattributes` (nuevo) | Un solo fin de línea (LF) en el repositorio; antes había archivos CRLF y LF mezclados. |
| `requirements*.in/.txt`, `pyproject.toml` | `redis`, `fakeredis` (pruebas), marcador de pruebas `sin_validar`. |
| `README.md`, `docs/MANUAL.md`, `docs/README.md` | Al día con ERS v2.1, BD v3 y Redis v2: arranque, estructura, catálogo de errores, reglas delicadas, variables, receta de migraciones, pendientes y catálogo de endpoints. |

## A · Acceso y cuentas, e I · Enlace público — Jeferson

| Archivo | Cambio | Requisito |
|---|---|---|
| `core/cache.py` (nuevo) | Sesión en Redis (`safetrace:sesion:<hash>`), conjunto de sesiones por usuario y caché de permisos de 300 s. | Redis v2 §6.1-6.2 |
| `core/limite.py` (nuevo) | Inicio de sesión: 5 fallos por IP+correo y 30 por IP en 15 min, **antes** de bcrypt; enlace público 60/min; verificación 30/min; recuperación 5/h por IP. Sin Redis no hay límites. | Redis v2 §6.3, RC-2026-010 (RNF-40 propuesto) |
| `app/crud/usuarios.py` | Sesiones: Redis primero, Mongo renovado cada 5 min; cerrar sesión, desactivar, cambiar rol o restablecer contraseña las borra de los dos. Recuperación de contraseña. `crear_administrador`. `schema_version` 3. | RNF-11, RF-73, RF-74 |
| `app/crud/permisos.py`, `modulo_permisos.py`, `modulos.py` | Caché de permisos con invalidación al cambiarlos. Nadie tiene `borrar` en los 7 módulos de historial (`BORRAR_NO_PERMITIDO`). | BD v3 6.8 (C-02) |
| `app/router/auth.py`, `app/schemas/auth.py` | `POST /auth/recuperacion` (202, misma respuesta exista o no el correo) y `POST /auth/recuperacion/restablecer` (204, un solo uso). | RF-73 |
| `app/router/usuarios.py`, `app/schemas/usuarios.py` | `POST /admin/administradores` solo para SUPERADMIN. El administrador general solo asigna PROPIETARIO o PERITO y no toca cuentas de administrador. | RF-74, RNF-08 |
| `trabajador/tareas/enviar_correo.py` (archivo de K) | Envía el enlace de recuperación; el token se genera justo antes de enviar y solo se guarda su hash. | RF-73 |
| `app/crud/enlaces.py`, `app/router/enlaces.py` | Las constancias del enlace usan la copia del perito guardada en la firma y el cálculo de vigencia de H; `revocado_por`; límite de 60/min en `/publico/{codigo}`. | RF-59 a RF-61 |
| `db/migraciones/0004_recuperaciones.py` | Colección `recuperaciones_contrasena` con validador e índices (TTL). | BD v3 6.3 |
| Pruebas | `tests/test_redis.py` (9), `tests/test_recuperacion_y_superadmin.py` (12). | |

**Supuesto para la PO:** las cuentas de administrador se crean con `consentimiento: null` y la persona lo acepta en su
primer inicio de sesión. Confirmarlo.

## B · Peritos y J · IA e índice — Brayan

| Archivo | Cambio | Requisito |
|---|---|---|
| `app/crud/peritos.py` | `ultima_asignacion_en` (desempate de la asignación), `candidatos_asignacion`, `marcar_asignacion` condicionada al valor leído. `schema_version` 3. | RF-49 |
| `app/schemas/peritos.py` | `especialidad` obligatoria (mínimo 3 caracteres). | RF-13 |
| `app/router/peritos.py` | Al validar un perito se reparten las solicitudes pendientes (llama a `servicios.inspecciones.repartir_pendientes`; así B no importa a H por dentro). Usa `router/comunes.py`. | RF-49 |
| `app/crud/ia_indice.py` | `schema_version` 3 en `analisis_ia` e `indices_priorizacion`. | BD v3 |
| `app/router/ia_indice.py` | `GET /inmuebles/{id}/indice/modelos` (gráficas) solo para el perito asignado y el administrador; el propietario recibe 403. | RNF-39 |
| `db/migraciones/0008_...` (con Nicolás) | `ultima_asignacion_en` null; se detiene si algún perito no tiene especialidad. | |
| Pruebas | `tests/test_indice.py` (RNF-39), `tests/test_archivos.py` (especialidad). | |

**Pendiente de Brayan:** el comparador de fotos (`cargar_modelo`, `comparar`) sigue sin implementar; los análisis
fallan tras 3 intentos y se pueden reintentar.

## C · Inmuebles y G · Estados — Valeria

| Archivo | Cambio | Requisito |
|---|---|---|
| `app/crud/inmuebles.py` | `quitar_ultimo_evento` (para la invalidación de eventos de D). `schema_version` 3. | RF-26 |
| `app/crud/estados.py` | `pedir_transicion(..., session=None)` para entrar en la transacción de la firma; `referencias_con_cambio` para que E calcule si una revisión cambió el estado. | RF-38 a RF-47 |

## D · Bitácora y K · Notificaciones — Mafe

| Archivo | Cambio | Requisito |
|---|---|---|
| `app/crud/bitacora.py`, `app/router/bitacora.py`, `app/schemas/bitacora.py` | Los eventos tienen `estado` (VIGENTE / INVALIDADO), `invalidacion` y `reemplazado_por`. `PATCH /eventos/{id}/invalidacion` con motivo, solo para eventos del propietario (los del SISTEMA, 403). Los invalidados no cuentan como antecedentes. Nunca se borran. | RNF-16, BD v3 8.1, BD-09 |
| `app/router/comunes.py` (nuevo) | `validar_zona` y `url_archivo`, que antes estaban en `router/bitacora.py` y que B y E importaban de ahí. | Estructura v2 |
| `app/crud/notificaciones.py`, `app/router/notificaciones.py`, `app/schemas/notificaciones.py` | Tipo `SOLICITUD_ASIGNADA`, `canales` [CORREO, APP], `leida_en`. Centro de notificaciones: `GET /notificaciones/no-leidas`, `PATCH /notificaciones/{id}/lectura`, `POST /notificaciones/lectura`. `GET /tareas/{id}` solo para quien puede ver el recurso de la tarea. | RF-69, RF-75 |
| `db/migraciones/0005_notificaciones.py` | Las notificaciones anteriores quedan con `canales: ["CORREO"]`; va **antes** del código. | |
| `db/migraciones/0007_eventos.py` | Validador de eventos (los v2 sin `estado` cuentan como VIGENTE). | |
| Pruebas | `tests/test_modulos_v3.py` (invalidación y centro de notificaciones). | |

## E · Revisión del propietario, F · Sismos y base de datos — Nicolás

| Archivo | Cambio | Requisito |
|---|---|---|
| `app/crud/revisiones.py` | Ya no guarda `cambio_estado_aplicado`: se calcula al leer con el historial de G. Las revisiones v2 conservan su valor guardado. | BD v3 8.3 |
| `app/router/revisiones.py` | Usa `router/comunes.py`. | |
| `app/crud/configuracion.py`, `app/crud/sismos.py`, `app/schemas/sismos.py` | El emparejamiento SGC/USGS (120 s, 100 km) sale de `configuracion.parametros_sismo.emparejamiento`; cada sismo guarda los parámetros que se le aplicaron. | RF-32 |
| `db/validadores/` (24 `$jsonSchema`) y `db/validacion.py` | Los validadores de la sección 12.1 que no se habían entregado. `python -m db.validacion --revisar` cuenta los documentos que no cumplen, sin cambiar nada. | BD v3 12.1 |
| `db/migraciones/` (0001 a 0009 y su README) | Una migración por cambio, con dueño, simulación sin `--aplicar`, repetibles y que se detienen ante datos que debe corregir una persona. | BD v3 §14, RNF-22 |
| `db/indices.py` | Índices de la v3; los dos parciales de 11.3 aparte con `--con-parciales`. | BD v3 11 |
| `db/semillas.py` | `emparejamiento`, `modulo_ers` por módulo, `asignacion_peritos` del administrador solo en consulta. | |
| Pruebas | `tests/conftest.py` (revisión de validadores en cada prueba), `tests/test_migraciones.py` (9). | |

**Pendiente de Nicolás:** ejecutar las migraciones contra `safetrace_test` y luego en Atlas (tras cambiar las
credenciales), crear los índices parciales y hacer la prueba de restauración (M0 no tiene respaldos automáticos).

## H · Inspecciones y constancias — Juan Miguel

| Archivo | Cambio | Requisito |
|---|---|---|
| `app/servicios/inspecciones.py` (reglas, nuevo contenido) | Primera capa de servicios con reglas reales. Asignación automática y justa; sin reasignación manual. Firma en una transacción. Corrección = nueva versión en borrador con sus propios 6 meses. Vencimiento diario solo para la versión activa. | RF-48 a RF-58, RF-72 |
| `app/crud/inspecciones.py` (solo datos) | Estados PENDIENTE_ASIGNACION → ASIGNADA → ATENDIDA. La inspección firmada ya no se modifica: `estado_constancia`, `es_version_activa` y `reemplazada_por_version` se calculan al leer. La huella SHA-256 cubre la copia del perito y la constancia. | RNF-13 |
| `app/router/inspecciones.py`, `app/schemas/inspecciones.py` | Se quitó `POST /admin/solicitudes-inspeccion/{id}/asignacion`. Tipos POSTERIOR_SISMO, SEGUIMIENTO, DANO_REPORTADO; motivo y fecha propuesta obligatorios (no anterior a hoy). Observaciones solo para propietario, perito firmante y administrador. Verificación pública con límite de 30/min. | RF-48, RF-58, RNF-38 |
| `db/migraciones/0009_modulo_h.py` | Validadores e índices de solicitudes e inspecciones; se detiene si hay estados viejos. | |
| Pruebas | `tests/test_inspecciones.py` (18), `tests/test_flujo_sismo.py` (flujo completo con asignación automática), `tests/unit/test_constancias.py`. Se borró `tests/test_reglas_inspeccion.py` (probaba la asignación manual). | |

## Pruebas compartidas ajustadas

`tests/test_casos_auditoria.py`, `test_acceso_perito.py`, `test_propagacion.py`, `test_trabajador.py`: nuevos estados de
H, `especialidad` y el marcador `sin_validar` en las 4 pruebas que insertan a mano documentos incompletos a propósito.

---

## Decisiones para la PO (Diseño DataBase v3, 11.2)

Implementadas como su propuesta; si la PO decide otra cosa, cambia poco código.

| Decisión | Cómo quedó |
|---|---|
| BD-03 | Desde el estado 1 o 5 la solicitud se crea sin cambiar el estado (1 → 4 y 5 → 4 no están en la máquina). |
| BD-04 | Si un sismo movió el inmueble mientras había una solicitud abierta, la firma se guarda y el estado no cambia. |
| BD-05 | Máximo una solicitud abierta por inmueble. |
| BD-06 | La verificación por QR muestra solo tipo y ciudad del inmueble. |
| BD-09 | La invalidación de eventos **ya quedó implementada** (la propuesta era dejarla para después del 25 nov si no alcanzaba). La PO decide si se queda en el MVP. |

## Pendientes que no se resolvieron aquí

- Capa de servicios: solo H tiene sus reglas en `app/servicios/`; en los demás módulos siguen en `app/crud/` y cada dueño las mueve sin cambiar el comportamiento (ADR 0017).
- Pruebas de integración contra `safetrace_test`: mongomock no ejecuta transacciones, validadores ni índices parciales.
- Comparador de fotos de la IA (Brayan), proveedor de correo y bucket de archivos de producción.
- BD-07 (opciones del enlace público) y BD-08 (línea cronológica con `$unionWith`): sin cambios en el código.
- RC-2026-010 (Redis, límites y vida máxima del token) aprobada por Brayan pero aún sin registrar en el formato; la ERS v2.2 debe recogerla.
