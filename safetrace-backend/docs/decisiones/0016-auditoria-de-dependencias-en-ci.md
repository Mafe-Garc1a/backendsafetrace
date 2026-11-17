# Auditoría de dependencias en la CI y Dependabot

**Fecha:** 2026-11-16

**Decisión:** La CI ejecuta `pip-audit -r requirements.txt` después de las pruebas y falla si encuentra una vulnerabilidad conocida. También corre cada lunes, aunque no haya cambios. Dependabot revisa cada semana `pip` y GitHub Actions; agrupa las actualizaciones menores en un solo pull request. La CI usa Python 3.13, la versión con la que `pip-compile` generó los `.txt`. Los `.txt` no llevan hashes.

**Motivo:** Lo pidió la evaluación (criterio 5). Una vulnerabilidad nueva puede aparecer sin que cambie el código, por eso la ejecución semanal. Con otra versión de Python, pip podría resolver dependencias distintas a las del archivo de bloqueo. No se usan hashes porque `requirements-dev.in` se restringe con `-c requirements.txt` y Dependabot regenera los archivos; se puede revisar después del MVP.
