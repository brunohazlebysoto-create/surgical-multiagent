import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Configuración de base
    app_name: str = "Surgical Multi-Agent Pipeline"
    debug: bool = False

    # API Keys (a cargar del .env)
    gemini_api_key: str = ""

    class Config:
        env_file = ".env"

# For backwards compatibility with the rest of the application that expects these globals
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración de API
# Cargar claves de API de Gemini (acepta una lista separada por comas)
gemini_keys_str = os.getenv("GEMINI_API_KEYS", "")
if gemini_keys_str:
    GEMINI_API_KEYS = [k.strip() for k in gemini_keys_str.split(",") if k.strip()]
else:
    single_key = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_KEYS = [single_key] if single_key else []

# Para compatibilidad con referencias heredadas de clave única
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""

# Modelos por defecto
# gemini-2.5-flash es el modelo recomendado para cuota gratuita por su balance de velocidad, contexto y razonamiento.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Tasa límite (Rate Limit) de la API gratuita (15 RPM)
# Usaremos un semáforo con un número controlado de reintentos
GEMINI_MAX_CONCURRENT_CALLS = 3
GEMINI_PAUSE_SECONDS = 4.5  # Pausa entre turnos de debate para regular la cuota y facilitar la lectura en el frontend

# Contraseña de acceso opcional para la aplicación
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "")
