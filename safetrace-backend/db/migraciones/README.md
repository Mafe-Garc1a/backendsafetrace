# Migraciones del Diseño DataBase v3 (sección 14; RNF-22)

Nueve migraciones pequeñas, una por cambio. Cada una:

- sin `--aplicar` solo muestra lo que haría; con `--aplicar` lo hace;
- se puede repetir sin efecto si ya se aplicó;
- se corre con el usuario administrador de Atlas, desde el computador de quien la corre (nunca desde la API ni n8n).

**Antes de la primera:** cambiar las credenciales que circularon en el zip (contraseña de Atlas, `JWT_SECRET`,
credencial de n8n) y probar todo en `safetrace_test` (variable `MONGO_DB`).

| # | Migración | Qué hace | Cuándo | Dueño |
|---|-----------|----------|--------|-------|
| 0001 | `0001_quitar_borrar_en_historial` | Sin `borrar` en los 7 módulos de historial | Ya | Nicolás |
| 0002 | `0002_crear_validadores` | Validadores de las 15 colecciones que no cambian de forma | Ya, tras `--revisar` | Nicolás |
| 0003 | `0003_indices` | 10 índices nuevos y quita los que sobran | Ya | Nicolás |
| 0004 | `0004_recuperaciones` | Colección `recuperaciones_contrasena` (RF-73) | Antes del código de RF-73 | Jeferson (A) |
| 0005 | `0005_notificaciones` | `SOLICITUD_ASIGNADA`, `canales`, `leida_en` (RF-75) | **Antes** del código | Mafe (K) |
| 0006 | `0006_revisiones` | Deja de exigir `cambio_estado_aplicado` | **Antes** del código | Nicolás (E) |
| 0007 | `0007_eventos` | `estado`, `reemplazado_por`, `invalidacion` | Después del código | Mafe (D) |
| 0008 | `0008_peritos_modulos_configuracion` | `ultima_asignacion_en`, `modulo_ers`, `emparejamiento`; especialidad obligatoria | Con el código de B | Brayan (B) y Nicolás |
| 0009 | `0009_modulo_h` | Validadores de solicitudes e inspecciones (sección 9) | Cuando H esté en main | Juan Miguel (H) |

Orden de comandos (sección 14.4):

```
python -m db.indices
python -m db.migraciones.0001_quitar_borrar_en_historial --aplicar
python -m db.validacion --revisar
python -m db.migraciones.0002_crear_validadores --aplicar
python -m db.migraciones.0003_indices --aplicar
# luego cada una en su pull request: python -m db.migraciones.000N_<nombre> --aplicar
```

Los dos índices únicos parciales (sección 11.3) se crean aparte, después de probarlos en `safetrace_test`:
`python -m db.indices --con-parciales`.
