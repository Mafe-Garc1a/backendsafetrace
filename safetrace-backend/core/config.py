"""Configuración leída de variables de entorno (archivo .env en local)."""

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# librería en Python que permite cargar variables de entorno desde el archivo .env
load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "SafeTrace"
    PROJECT_VERSION: str = "0.1.0"
    PROJECT_DESCRIPTION: str = "Bitácora de inmuebles, sismos e inspecciones"

    # Entorno de ejecución (local | pruebas | produccion)
    ENTORNO: str = os.getenv("ENTORNO", "local")

    # Configuración de la base de datos (MongoDB Atlas o MongoDB instalado en el equipo)
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "safetrace")

    # Conexiones máximas por proceso; total = (procesos web + trabajadores) × este valor
    mongo_max_pool_size: int = int(os.getenv("MONGO_MAX_POOL_SIZE", "20"))

    # Tiempos máximos en milisegundos: conectar, esperar una respuesta y esperar una conexión libre
    mongo_connect_timeout_ms: int = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "5000"))
    mongo_socket_timeout_ms: int = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "15000"))
    mongo_wait_queue_timeout_ms: int = int(os.getenv("MONGO_WAIT_QUEUE_TIMEOUT_MS", "5000"))

    # Configuración JWT
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    # Duración máxima del token; la sesión además se cierra tras MINUTOS_SESION sin actividad
    jwt_access_token_expire_minutes: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    # Sesiones: se cierran solas tras 30 minutos sin actividad (RNF-11)
    minutos_sesion: int = int(os.getenv("MINUTOS_SESION", "30"))

    # Una tarea con más de este tiempo en PROCESANDO se considera abandonada por un trabajador caído
    minutos_tarea_atascada: int = int(os.getenv("MINUTOS_TAREA_ATASCADA", "15"))

    # Tiempo máximo de una tarea; debe ser menor que MINUTOS_TAREA_ATASCADA
    segundos_maximos_tarea: int = int(os.getenv("SEGUNDOS_MAXIMOS_TAREA", "300"))

    # Fallos seguidos de un proveedor antes de dejar de llamarlo, y por cuánto tiempo
    fallos_maximos_proveedor: int = int(os.getenv("FALLOS_MAXIMOS_PROVEEDOR", "5"))
    segundos_circuito_abierto: int = int(os.getenv("SEGUNDOS_CIRCUITO_ABIERTO", "60"))

    # n8n entra a /interno/* con esta credencial (encabezado X-Credencial-Servicio)
    credencial_servicio_n8n: str = os.getenv("CREDENCIAL_SERVICIO_N8N", "cambiar")

    # Primer administrador general (lo crea `python -m db.semillas`)
    admin_correo: str = os.getenv("ADMIN_CORREO", "")
    admin_contrasena: str = os.getenv("ADMIN_CONTRASENA", "")

    # Superadministrador: tiene todos los permisos (lo crea `python -m db.semillas`)
    superadmin_correo: str = os.getenv("SUPERADMIN_CORREO", "")
    superadmin_contrasena: str = os.getenv("SUPERADMIN_CONTRASENA", "")

    # Proveedor de archivos compatible con S3 (Cloudflare R2, AWS S3 o MinIO en local)
    # URL del API S3, sin el bucket. R2: https://<cuenta>.r2.cloudflarestorage.com · MinIO: http://localhost:9000
    proveedor_archivos_url: str = os.getenv("PROVEEDOR_ARCHIVOS_URL", "")
    archivos_bucket: str = os.getenv("ARCHIVOS_BUCKET", "")
    archivos_access_key: str = os.getenv("ARCHIVOS_ACCESS_KEY", "")
    archivos_secret_key: str = os.getenv("ARCHIVOS_SECRET_KEY", "")
    # R2: auto · MinIO: us-east-1 · S3: la región del bucket
    archivos_region: str = os.getenv("ARCHIVOS_REGION", "auto")
    archivos_tamano_maximo_mb: int = int(os.getenv("ARCHIVOS_TAMANO_MAXIMO_MB", "10"))
    # Vigencia de las URL firmadas de subida y de lectura, y tiempo máximo de una descarga del trabajador
    archivos_segundos_subida: int = int(os.getenv("ARCHIVOS_SEGUNDOS_SUBIDA", "600"))
    archivos_segundos_lectura: int = int(os.getenv("ARCHIVOS_SEGUNDOS_LECTURA", "900"))
    archivos_segundos_timeout: int = int(os.getenv("ARCHIVOS_SEGUNDOS_TIMEOUT", "20"))

    correo_api_key: str = os.getenv("CORREO_API_KEY", "")

    # Dirección del frontend: arma el enlace de recuperación de contraseña (RF-73)
    url_frontend: str = os.getenv("URL_FRONTEND", "http://localhost:5173")

    # Recuperación de contraseña (RF-73): enlace de un solo uso, 60 minutos, máximo 3 por usuario por hora
    minutos_recuperacion: int = int(os.getenv("MINUTOS_RECUPERACION", "60"))
    recuperaciones_max_por_hora: int = int(os.getenv("RECUPERACIONES_MAX_POR_HORA", "3"))

    # Redis (Integración Redis v2, RC-2026-010): sesiones, permisos y límites. Vacío: todo funciona con MongoDB
    redis_url: str = os.getenv("REDIS_URL", "")
    redis_prefijo: str = os.getenv("REDIS_PREFIJO", "safetrace")
    permisos_cache_segundos: int = int(os.getenv("PERMISOS_CACHE_SEGUNDOS", "300"))
    # MongoDB renueva `sesiones.expira_en` como máximo cada este tiempo (Diseño DataBase v3, 6.2)
    sesion_renovar_mongo_segundos: int = int(os.getenv("SESION_RENOVAR_MONGO_SEGUNDOS", "300"))
    login_max_intentos: int = int(os.getenv("LOGIN_MAX_INTENTOS", "5"))
    login_max_intentos_ip: int = int(os.getenv("LOGIN_MAX_INTENTOS_IP", "30"))
    login_ventana_segundos: int = int(os.getenv("LOGIN_VENTANA_SEGUNDOS", "900"))
    publico_max_por_minuto: int = int(os.getenv("PUBLICO_MAX_POR_MINUTO", "60"))
    verificar_max_por_minuto: int = int(os.getenv("VERIFICAR_MAX_POR_MINUTO", "30"))
    recuperar_max_por_hora_ip: int = int(os.getenv("RECUPERAR_MAX_POR_HORA_IP", "5"))


settings = Settings()
if not settings.jwt_secret:
    raise RuntimeError("Falta JWT_SECRET en las variables de entorno")
