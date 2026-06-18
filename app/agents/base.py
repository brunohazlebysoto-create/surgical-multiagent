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

# Variable de contexto para almacenar llaves de API Gemini específicas de la ejecución actual (seguro contra asincronía)
gemini_keys_context = contextvars.ContextVar("gemini_keys", default=None)

# Variable de contexto para el modelo Gemini seleccionado por el usuario (por ejecución)
gemini_model_context = contextvars.ContextVar("gemini_model", default=None)

async def call_gemini(
    prompt: str,
    system_instruction: Optional[str] = None,
    json_mode: bool = False,
    temperature: float = 0.2,
    inline_data: Optional[dict] = None,
    thinking_budget: int = 1024,
    timeout: float = 30.0,
    max_output_tokens: Optional[int] = None
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

    # Budget de razonamiento: 0=sin thinking, 1024=mínimo, 8192=normal, -1=ilimitado
    # Valor por defecto 1024: permite algo de razonamiento sin causar demoras de minutos
    contents["generationConfig"]["thinkingConfig"] = {"thinkingBudget": thinking_budget}

    # Límite de tokens de salida. CRÍTICO en Gemini 2.5: el thinkingBudget se descuenta
    # del presupuesto total, así que generaciones largas (ej. 40-60 diapositivas) necesitan
    # un máximo alto y explícito para no truncar el JSON a medias y caer en el fallback.
    if max_output_tokens:
        contents["generationConfig"]["maxOutputTokens"] = max_output_tokens

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

    # Estrategia de reintentos diferenciada:
    #   - 429 (quota): rotar clave y reintentar hasta num_keys * 3 veces — las claves pueden
    #     recuperarse y hay múltiples claves disponibles.
    #   - Timeout / error de red: fallar RÁPIDO. Un timeout significa que la API no respondió
    #     en el tiempo acordado; reintentar num_keys*3 veces × timeout = cuelgue de minutos.
    #     Aquí solo reintentamos 1 vez por clave y luego abandonamos.
    max_quota_attempts = num_keys * 3   # para 429s: probar todas las claves varias veces
    max_timeout_failures = num_keys     # para timeouts: probar cada clave una sola vez
    max_json_failures = 3               # para JSON inválido: no martillear la API indefinidamente
    backoff = 3.0
    consecutive_timeout_failures = 0
    json_parse_failures = 0

    async with _api_semaphore:
        for attempt in range(max_quota_attempts):
            key_idx = _current_key_idx % num_keys
            api_key = keys_to_use[key_idx]

            if not api_key or "Placeholder" in api_key or api_key.startswith("KEY"):
                logger.warning(f"Llave Gemini en el índice {key_idx} es un placeholder o está vacía. Rotando al instante...")
                _current_key_idx = (_current_key_idx + 1) % num_keys
                continue

            # streamGenerateContent + alt=sse: los tokens (pensamiento + salida) llegan de
            # forma incremental. Esto evita el cuelgue de las llamadas no-streaming, donde el
            # servidor procesaba TODO en silencio y el timeout no podía distinguir "pensando"
            # de "colgado". Con streaming, el read-timeout solo vigila el HUECO entre chunks,
            # así que podemos permitir presupuestos de pensamiento altos sin riesgo de cuelgue.
            model_to_use = gemini_model_context.get() or GEMINI_MODEL
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_to_use}:streamGenerateContent?alt=sse&key={api_key}"

            try:
                import json as _json
                # read = máximo hueco permitido entre chunks (cubre la fase de pensamiento inicial).
                # El tope total de pared lo impone el asyncio.wait_for del llamador.
                timeout_obj = httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0)
                text_response = ""
                async with httpx.AsyncClient(timeout=timeout_obj) as client:
                    async with client.stream("POST", url, json=contents) as response:
                        if response.status_code == 429:
                            await response.aread()
                            logger.warning(
                                f"Límite de cuota (429) para llave {key_idx}. "
                                f"Rotando... (Intento {attempt + 1}/{max_quota_attempts})"
                            )
                            consecutive_timeout_failures = 0  # 429 ≠ timeout, resetear contador
                            _current_key_idx = (_current_key_idx + 1) % num_keys
                            if (attempt + 1) % num_keys == 0:
                                logger.info(f"Carrusel completo de {num_keys} llaves. Esperando {backoff}s...")
                                await asyncio.sleep(backoff)
                                backoff *= 1.5
                            continue

                        if response.status_code != 200:
                            await response.aread()  # leer cuerpo de error antes de raise
                        response.raise_for_status()

                        # Acumular el texto de todos los eventos SSE conforme llegan
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            payload = line[5:].strip()
                            if not payload or payload == "[DONE]":
                                continue
                            try:
                                chunk = _json.loads(payload)
                            except Exception:
                                continue
                            for cand in chunk.get("candidates", []):
                                parts = (cand.get("content") or {}).get("parts", []) or []
                                for part in parts:
                                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                                        text_response += part["text"]

                consecutive_timeout_failures = 0  # éxito: resetear
                text_response = text_response.strip()

                if not text_response:
                    logger.error("El stream de Gemini no devolvió texto.")
                    return '{"error": "Respuesta vacía o incorrecta"}' if json_mode else "Error: respuesta de API inválida."

                if json_mode:
                    try:
                        cleaned = text_response.lstrip("```json").lstrip("```").rstrip("```").strip()
                        _json.loads(cleaned)
                        return cleaned
                    except (_json.JSONDecodeError, ValueError):
                        json_parse_failures += 1
                        logger.warning(
                            f"JSON inválido en intento {attempt + 1} "
                            f"(fallo de parseo {json_parse_failures}/{max_json_failures})."
                        )
                        # No martillear la API: si el modelo insiste en JSON malformado,
                        # abandonar pronto para que el llamador caiga a su fallback determinista.
                        if json_parse_failures >= max_json_failures:
                            raise Exception(
                                "El modelo devolvió JSON inválido repetidamente "
                                f"({max_json_failures} veces). Abortando para usar fallback."
                            )
                        await asyncio.sleep(1.5)
                        continue

                return text_response

            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP (Intento {attempt + 1}, Llave {key_idx}): {e.response.status_code}")
                consecutive_timeout_failures += 1
                _current_key_idx = (_current_key_idx + 1) % num_keys
                if consecutive_timeout_failures >= max_timeout_failures:
                    raise Exception(f"Todas las claves devolvieron errores HTTP. Último: {e.response.status_code}")
                if (attempt + 1) % num_keys == 0:
                    await asyncio.sleep(backoff)
                    backoff *= 1.5

            except httpx.RequestError as e:
                # Timeout, DNS, conexión rechazada — fallar rápido
                consecutive_timeout_failures += 1
                logger.error(f"Error de red/timeout (Intento {attempt + 1}, Llave {key_idx}): {type(e).__name__}")
                _current_key_idx = (_current_key_idx + 1) % num_keys
                if consecutive_timeout_failures >= max_timeout_failures:
                    raise Exception(f"Timeout o error de red en todas las claves ({max_timeout_failures} intentos). Verifica conectividad y cuota.")
                # Pausa breve antes de intentar la siguiente clave
                await asyncio.sleep(1.0)

        raise Exception("Se agotaron todos los reintentos para la API de Gemini.")


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
        """Formatea un mensaje de log para enviarlo al frontend."""
        return {
            "type": "log",
            "agent": self.name,
            "role": self.role,
            "text": text,
            "stage": stage,
            "color": self.color,
            "icon": self.icon
        }
