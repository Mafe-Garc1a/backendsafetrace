# Capa de servicios y contratos de dependencia

**Fecha:** 2026-11-16

**Decisión:** Se crea `app/servicios/` con un archivo por módulo de la ERS (Estructura del backend v2, sección 2). Cada archivo indica su dueño, lo que ofrece a los demás módulos (Arquitectura v2, tabla 5.1) y a qué servicios puede llamar (matriz 5.2). Por ahora las reglas siguen en `app/crud/`: cada dueño las mueve a su servicio sin cambiar el comportamiento. Las rutas `/` y `/salud` pasan de `main.py` a `app/router/salud.py`. `import-linter` comprueba en la CI dos contratos definidos en `pyproject.toml`: el orden de capas `app.router` → `app.servicios` → `app.crud`, y que `core` no importe `app` ni `trabajador` (AUD-01). La CI también ejecuta `ruff format --check .` (AUD-10); para que pase, se aplicó `ruff format` a 13 archivos, con cambios solo de formato.

**Motivo:** Con los contratos en la CI, la estructura deja de depender de que cada persona la recuerde: una importación en sentido contrario hace fallar la CI. Crear los archivos vacíos fija desde ya el dueño y los límites de cada módulo, y no toca las reglas delicadas antes del MVP, lo que mantiene la decisión del ADR 0015. El contrato de capas permite que un router llame al `crud` directamente mientras dura la transición.
