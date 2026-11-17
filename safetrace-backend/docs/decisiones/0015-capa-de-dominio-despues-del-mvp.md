# Capa de dominio y repositorios después del MVP

**Fecha:** 2026-11-16

**Decisión:** No se introduce la capa de dominio (`app/dominio/`) ni los repositorios por colección (`app/repositorios/`) antes de la entrega del MVP, y `crud/inspecciones.py` (357 líneas) no se divide. Se mantienen las capas actuales: router → crud → core. Cuando se retome, se empieza por inspecciones y estados, como propone la evaluación.

**Motivo:** La evaluación (criterio 6, fase 3) los clasifica como esfuerzo alto y acepta dejarlos como recomendación. Tocan las reglas más delicadas (firma, constancias y transiciones de estado) a pocos días de la entrega final, y las pruebas corren sobre mongomock, no sobre un MongoDB real. Hoy el riesgo de introducir un error es mayor que el beneficio. Las reglas siguen teniendo un solo dueño: solo `crud.estados.pedir_transicion` cambia el estado de un inmueble.
