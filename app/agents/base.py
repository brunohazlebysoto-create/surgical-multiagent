import asyncio
import logging
import httpx
import contextvars
from typing import Dict, Any, Optional
from app.core.config import GEMINI_API_KEYS, GEMINI_MODEL, GEMINI_PAUSE_SECONDS

# Configurar logging básico para depurar en consola
logger = logging.getLogger("multiagent_base")
logging.basicConfig(level=logging.INFO)

# Semáforo global para controlar la concurrencia a nivel de aplicación (evita saturar el free tier)
_api_semaphore = asyncio.Semaphore(3)

# Índice global para rotar las API Keys entre las llamadas concurrentes
_current_key_idx = 0

# Lock para proteger la rotación de clave de race conditions en contexto async
_key_rotation_lock = asyncio.Lock()

# Variable de contexto para almacenar llaves de API Gemini específicas de la ejecución actual (seguro contra asincronía)
gemini_keys_context = contextvars.ContextVar("gemini_keys", default=None)

async def call_gemini(
    prompt: str,
    system_instruction: Optional[str] = None,
    json_mode: bool = False,
    temperature: float = 0.2,
    inline_data: Optional[dict] = None
) -> str:
    """
    Función base asíncrona para realizar llamadas a la API de Google Gemini sin SDKs,
    usando httpx con rotación secuencial de llaves en caso de error 429 y semáforo de concurrencia.
    Soporta la lectura de llaves desde un ContextVar para aislamiento entre usuarios.
    """
    global _current_key_idx

    # Determinar qué grupo de llaves usar (las del contexto del cliente o las globales)
    keys_to_use = gemini_keys_context.get()
    if keys_to_use is None or len(keys_to_use) == 0:
        keys_to_use = GEMINI_API_KEYS

    if not keys_to_use:
        logger.error("No se han configurado llaves de Gemini (GEMINI_API_KEYS en .env o pasadas por el cliente).")
        return '{"error": "API Keys no configuradas"}' if json_mode else "Error: API Keys no configuradas"

    num_keys = len(keys_to_use)

    # Preparar el cuerpo de la petición (común para cualquier clave)
    contents = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
        }
    }
    
    if inline_data:
        contents["contents"][0]["parts"].append({
            "inlineData": inline_data
        })
        
    if system_instruction:
        contents["systemInstruction"] = {
            "parts": [
                {"text": system_instruction}
            ]
        }
        
    if json_mode:
        contents["generationConfig"]["responseMimeType"] = "application/json"

    # Pacing de UI y Rate Limit: Pausa estratégica para regular la tasa antes de la llamada
    await asyncio.sleep(GEMINI_PAUSE_SECONDS)

    # Reintentos totales: cada clave puede intentarse hasta 3 veces
    max_attempts = num_keys * 3
    backoff = 3.0  # Backoff de seguridad si todas las claves fallan consecutivamente

    async with _api_semaphore:
        for attempt in range(max_attempts):
            # Leer el índice actual de forma atómica
            async with _key_rotation_lock:
                key_idx = _current_key_idx % num_keys
                api_key = keys_to_use[key_idx]

            # Si es un placeholder, rotarla inmediatamente y continuar
            if not api_key or "Placeholder" in api_key or api_key.startswith("KEY"):
                logger.warning(f"Llave Gemini en el índice {key_idx} es un placeholder o está vacía. Rotando al instante...")
                async with _key_rotation_lock:
                    _current_key_idx = (_current_key_idx + 1) % num_keys
                continue

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
            
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, json=contents)
                    
                    # Si da error de tasa límite (429), rotar clave de inmediato
                    if response.status_code == 429:
                        logger.warning(
                            f"Límite de cuota (429) alcanzado para la llave {key_idx}. "
                            f"Rotando al instante a la siguiente clave... (Intento {attempt + 1}/{max_attempts})"
                        )
                        async with _key_rotation_lock:
                            _current_key_idx = (_current_key_idx + 1) % num_keys
                        
                        # Si hemos dado una vuelta completa a todas las llaves, dormir un momento
                        if (attempt + 1) % num_keys == 0:
                            logger.info(f"Se probó el carrusel completo de {num_keys} llaves. Esperando {backoff}s antes de reintentar...")
                            await asyncio.sleep(backoff)
                            backoff *= 1.5
                        continue
                        
                    response.raise_for_status()
                    
                    data = response.json()
                    # Extraer el texto de la respuesta
                    try:
                        text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                        return text_response.strip()
                    except (KeyError, IndexError) as err:
                        logger.error(f"Estructura de respuesta inesperada de Gemini API: {data}. Error: {err}")
                        return '{"error": "Respuesta vacía o incorrecta"}' if json_mode else "Error: Estructura de respuesta de API inválida."
                        
            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP de API Gemini (Intento {attempt + 1}, Llave {key_idx}): {e.response.status_code} - {e.response.text}")
                
                async with _key_rotation_lock:
                    _current_key_idx = (_current_key_idx + 1) % num_keys
                
                if (attempt + 1) % num_keys == 0:
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    
            except httpx.RequestError as e:
                logger.error(f"Error de red al conectar con Gemini API (Intento {attempt + 1}, Llave {key_idx}): {e}")
                
                async with _key_rotation_lock:
                    _current_key_idx = (_current_key_idx + 1) % num_keys
                
                if (attempt + 1) % num_keys == 0:
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    
        raise Exception("Se agotaron todos los reintentos y llaves configuradas para la API de Gemini.")


class BaseAgent:
    """
    Clase base para todos los agentes virtuales.
    Facilita el formateo de logs de debate que serán transmitidos por SSE.
    """
    def __init__(self, name: str, role: str, color: str, icon: str):
        self.name = name          # Ej: "Buscador Principal"
        self.role = role          # Ej: "Ejecutor" o "Crítico"
        self.color = color        # Código de color HEX para la interfaz (ej: "#38bdf8")
        self.icon = icon          # Ícono FontAwesome o Emoji (ej: "🔍")

    def format_log(self, text: str, stage: str) -> Dict[str, Any]:
        """
        Formatea la respuesta para enviarla a la cola SSE y renderizarla en el chat.
        """
        return {
            "agent": self.name,
            "role": self.role,
            "color": self.color,
            "icon": self.icon,
            "stage": stage,
            "content": text
        }
