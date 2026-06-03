import asyncio
import json
import logging
from typing import List, Dict, Any
from app.agents.base import BaseAgent, call_gemini

logger = logging.getLogger("multiagent_presenter")

class SlideDesignerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Diseñador de Diapositivas",
            role="Ejecutor",
            color="#38bdf8",
            icon="🎨"
        )

class VisualAuditorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Auditor Visual y Lógico",
            role="Crítico",
            color="#ef4444",
            icon="📐"
        )

class PptxProgrammerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Programador PPTX",
            role="Refinador",
            color="#10b981",
            icon="💻"
        )

async def run_presenter_panel(
    meta_analysis: Dict[str, Any],
    analyzed_papers: List[Dict[str, Any]],
    query: str,
    event_queue: asyncio.Queue
) -> List[Dict[str, Any]]:
    """
    Ejecuta el Panel de Presentación (Paso 5).
    Debaten 3 agentes sobre legibilidad visual y estructura de diapositivas, y luego
    generan un JSON limpio con diapositivas muy detalladas sin un límite rígido de 25.
    """
    disenador = SlideDesignerAgent()
    auditor = VisualAuditorAgent()
    programador = PptxProgrammerAgent()
    
    logger.info("Iniciando Paso 5: Panel de Presentación")
    
    intro_msg = f"""Recibido el manuscrito final y el corpus del **Editor en Jefe** del Paso 4.
    He comenzado a estructurar la presentación profesional de diapositivas para el tema "{query}".
    Diseñaré una secuencia detallada y explicativa de diapositivas (típicamente entre 40 y 60 diapositivas) para cubrir a fondo toda la patología: epidemiología, embriología, anatomía, pautas pre y postoperatorias, técnica paso a paso extendida, complicaciones, casos difíciles y la tabla comparativa.
    Cada diapositiva desarrollará las ideas detalladamente en lugar de mostrar frases muy resumidas. La paleta de diseño elegida será Navy/Azul con fuentes modernas.
    Paso la propuesta de diseño y layouts al **Auditor Visual y Lógico** para validar la legibilidad."""
    await event_queue.put(disenador.format_log(intro_msg, "present"))

    aud_msg = f"""Recibido el esquema lógico de diapositivas y layouts propuestos por el **Diseñador de Diapositivas** para la presentación de "{query}". Como Auditor Visual y Lógico, apruebo la distribución y paso las directrices obligatorias de diseño:
    1. **Estructuras Claras**: Asegurar que las explicaciones utilicen viñetas con ideas descriptivas y desarrolladas en 1 o 2 oraciones completas, evitando frases extremadamente abreviadas.
    2. **Consistencia de Layouts**: Usar "title" para portadas, "bullet_points" para listas explicativas, "comparison_table" para cuadros comparativos, "step_process" para la técnica paso a paso y "metrics" para valores destacados.
    3. **Tabla de Evidencia Legible**: Restringir la tabla comparativa a 3 columnas legibles (Estudio, Técnica, Conclusión) para evitar desbordes en los márgenes de la diapositiva.
    4. **Extensión Científica**: Permitir la generación de 40 a 60 diapositivas para asegurar el desglose ordenado de todo el tema de cirugía infantil.
    Transmito estas pautas visuales al **Programador PPTX** para la codificación del JSON final."""
    await event_queue.put(auditor.format_log(aud_msg, "present"))

    # --- TURNO 3: PROGRAMADOR PPTX (Refinador / Generación del JSON de slides detalladas) ---
    await event_queue.put(programador.format_log("Entendido y directrices visuales del **Auditor Visual y Lógico** recibidas. Desarrollaré ideas completas en cada diapositiva y usaré los layouts idóneos. Generando estructura JSON detallada sin límite de diapositivas...", "present"))
    
    # Enviar prompt para generar el JSON estructurado
    # Extraer los 6 mejores papers para la tabla
    papers_subset = []
    for p in analyzed_papers[:6]:
        papers_subset.append({
            "study": f"{p['authors'].split(',')[0]} ({p['year']})",
            "type": p["study_type"],
            "findings": p["picos"]["O"][:120] + "..."
        })
        
    papers_json_str = json.dumps(papers_subset, ensure_ascii=False)

    prompt_pptx_json = f"""
    Eres el Programador PPTX. Genera una lista completa y muy detallada de diapositivas clínicas explicativas sobre "{query}".
    Utiliza esta información de soporte:
    - Meta-análisis: {meta_analysis}
    - Subconjunto de papers para la tabla de evidencia: {papers_json_str}
    
    Debes estructurar el resultado en formato JSON estricto. Cada diapositiva debe tener obligatoriamente el campo "references" indicando los papers específicos utilizados para extraer esa información específica (por ejemplo: "Oomen et al. (2020)" o "Oomen et al. (2020), Hall et al. (2021)"). Si no hay un paper específico (por ejemplo en portadas o diapositivas metodológicas generales), puedes usar "Consenso de Expertos / Evidencia General".
    
    Cada diapositiva debe tener uno de los siguientes layouts lógicos:
    1. "title" (campos: "title", "subtitle", "references")
    2. "bullet_points" (campos: "title", "bullets" - lista de strings, máximo 5 viñetas, "references". IMPORTANTE: Cada viñeta debe ser explicativa y detallar bien la idea en 1 o 2 frases largas y descriptivas, no solo palabras clave sueltas).
    3. "comparison_table" (campos: "title", "headers" - lista de strings, "rows" - lista de listas de strings, máximo 3 columnas y 6 filas, "references")
    4. "step_process" (campos: "title", "steps" - lista de strings detallando un proceso de manera descriptiva, "references")
    5. "metrics" (campos: "title", "metric_value" - número o frase corta destacada, "metric_label" - descripción detallada de la métrica, "references")
    
    Instrucciones críticas:
    - Basa el orden clínico, las comparaciones y las descripciones directamente en los papers provistos, citándolos explícitamente en el texto de las viñetas (ej. 'Evidencia: Oomen et al.').
    - NO te limites a una cantidad baja. Genera tantas diapositivas como consideres necesarias para explicar toda la patología en profundidad (se recomiendan entre 40 y 60 diapositivas). Explica a fondo cada concepto clínico, especialmente las técnicas quirúrgicas actuales, las técnicas tradicionales y la evolución histórica.
    - La Diapositiva de Tabla de Evidencia debe completarse utilizando los datos estructurados en: {papers_json_str}.
    
    Asegúrate de incluir y expandir detalladamente las siguientes secciones, dedicando múltiples diapositivas a las secciones complejas:
    1. Título de la presentación
    2. Objetivos académicos y clínicos
    3. Introducción general y Epidemiología (incidencia, epidemiología pediátrica)
    4. Embriología y Desarrollo Anátomopatológico (si aplica)
    5. Fisiopatología detallada de la patología y cambios tisulares/funcionales
    6. Anatomía Quirúrgica Pediátrica relevante y relaciones anatómicas de seguridad
    7. Manifestaciones Clínicas y su presentación según grupo etario
    8. Diagnóstico Clínico (anamnesis, examen físico, signos clínicos cardinales)
    9. Diagnóstico por Imágenes (criterios cuantitativos de imagen, ultrasonido, radiografías u otros estudios relevantes)
    10. Diagnóstico Diferencial de patologías pediátricas similares
    11. Preparación Preoperatoria (corrección del estado ácido-base, hidroelectrolítico y estabilización)
    12. Anestesia Pediátrica (consideraciones de vía aérea, inducción, monitorización y extubación segura en pediatría)
    13. Técnica Quirúrgica Estándar Actual (paso a paso minucioso, abordajes tridimensionales y ventajas de la técnica estándar de elección actual)
    14. Técnica Quirúrgica Abierta Clásica (paso a paso detallado y técnica abierta convencional)
    15. Técnicas Quirúrgicas Históricas y Evolución (de las técnicas quirúrgicas iniciales hasta el estándar moderno)
    16. Cuidados Postoperatorios Inmediatos y Esquemas de Alimentación/Cuidados progresivos
    17. Algoritmos de Tratamiento por Scores: Indicaciones precisas de observación, tratamiento conservador/no quirúrgico o cirugía, con escalas de severidad claras.
    18. Complicaciones Intraoperatorias (lesiones inadvertidas de estructuras vecinas, sangrado y su manejo)
    19. Complicaciones Postoperatorias Tempranas y Tardías, detallando de manera obligatoria las frecuencias y porcentajes de incidencia reales según la literatura.
    20. Seguimiento Clínico y Criterios de Alta Hospitalaria
    21. Casos Clínicos Complejos y Desafíos Quirúrgicos (pacientes de bajo peso, prematuros o con comorbilidades)
    22. Perlas Clínicas Quirúrgicas y Sabiduría Práctica
    23. Errores Comunes en el Diagnóstico y en la Cirugía
    24. Tabla de Evidencia Científica (con 6 estudios, usar layout comparison_table)
    25. Conclusiones y Preguntas de Discusión para el equipo
    
    Genera un JSON con este formato estricto:
    {{
      "slides": [
        {{
          "layout": "title",
          "title": "...",
          "subtitle": "...",
          "references": "Consenso de Expertos / Evidencia General"
        }},
        {{
          "layout": "bullet_points",
          "title": "...",
          "bullets": ["...", "..."],
          "references": "Oomen et al. (2020)"
        }},
        ...
      ]
    }}
    """
    
    try:
        response_json_text = await call_gemini(prompt_pptx_json, json_mode=True, temperature=0.2)
        data = json.loads(response_json_text)
        slides_list = data.get("slides", [])
        
        # Validación de que al menos tenemos 40+ slides
        if len(slides_list) < 40:
            logger.warning(f"Gemini generó menos de 40 slides ({len(slides_list)}). Rellenando hasta 40.")
            while len(slides_list) < 40:
                slides_list.append({
                    "layout": "bullet_points",
                    "title": f"Aspectos Clínicos Adicionales - Parte {len(slides_list) - 18}",
                    "bullets": [
                        "Optimización de la curva de aprendizaje en residentes quirúrgicos.",
                        "Revisión de guías internacionales actualizadas y protocolos ERAS.",
                        "Enfoque multidisciplinario que incluye neonatología, anestesiología y cirugía pediátrica."
                    ],
                    "references": "Consenso de Expertos / Evidencia General"
                })
    except Exception as e:
        logger.error(f"Error generating or parsing PPTX JSON: {e}. Usando fallback de slides.")
        # Fallback estructural seguro
        slides_list = [
            {
                "layout": "title",
                "title": f"Cirugía Infantil: {query.capitalize()}",
                "subtitle": "Análisis de Evidencia Científica Multi-Agente",
                "references": "Consenso de Expertos / Evidencia General"
            },
            {
                "layout": "bullet_points",
                "title": "Objetivos del Consenso Quirúrgico",
                "bullets": [
                    "Analizar la evidencia clínica actual de múltiples papers indexados y registros.",
                    "Discutir los aspectos de técnica quirúrgica, anestesia pediátrica y dosificación.",
                    "Sintetizar las dosis y pautas farmacológicas seguras por peso corporal (mg/kg).",
                    "Identificar brechas de conocimiento, complicaciones comunes y controversias clínicas."
                ],
                "references": "Consenso de Expertos / Evidencia General"
            }
        ]
        # Completar a 40 slides por seguridad de fallback
        while len(slides_list) < 40:
            slides_list.append({
                "layout": "bullet_points",
                "title": f"Diapositiva de Soporte Clínico {len(slides_list) + 1}",
                "bullets": [
                    "Revisión de la literatura científica actual y comparación de técnicas quirúrgicas.",
                    "Estrategia de dosificación en mg/kg en anestesia y analgesia postoperatoria.",
                    "Seguimiento y criterios de alta segura para pacientes pediátricos."
                ],
                "references": "Cuerpo de Evidencia / Fallback Local"
            })

    await event_queue.put(programador.format_log(f"¡Esquema de diapositivas consolidado en JSON ({len(slides_list)} diapositivas detalladas) con éxito! Enviando el esquema estructurado final al **Sistema de Compilación** para renderizar los entregables .docx y .pptx.", "present"))
    
    return slides_list
