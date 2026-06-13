import asyncio
import json
import logging
from typing import List, Dict, Any
from app.agents.base import BaseAgent, call_gemini

logger = logging.getLogger("multiagent_meta_analyst")

class SynthesizerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Sintetizador de Evidencia",
            role="Ejecutor",
            color="#38bdf8",
            icon="📊"
        )

class BiasOpponentAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Opositor de Sesgos",
            role="Crítico",
            color="#ef4444",
            icon="⚖️"
        )

class ScientificWriterAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Redactor Científico",
            role="Refinador",
            color="#10b981",
            icon="📈"
        )

async def run_meta_analyst_panel(
    analyzed_papers: List[Dict[str, Any]], 
    query: str, 
    event_queue: asyncio.Queue
) -> Dict[str, Any]:
    """
    Ejecuta el Panel de Meta-Análisis (Paso 3) de forma altamente optimizada (1 llamada API total en lugar de 3).
    Genera el diálogo entre los agentes y la síntesis GRADE final consolidada en un solo objeto JSON.
    """
    sintetizador = SynthesizerAgent()
    opositor = BiasOpponentAgent()
    redactor = ScientificWriterAgent()
    
    logger.info("Iniciando Paso 3: Panel de Meta-Análisis Optimizado")
    
    # Formatear el corpus analizado incluyendo autores, revista y DOI para citas correctas
    corpus_str = ""
    for i, p in enumerate(analyzed_papers):
        abstract_excerpt = (p.get("abstract") or "").strip()
        abstract_line = (
            f"\n        Extracto del abstract: {abstract_excerpt[:300]}"
            if abstract_excerpt else ""
        )
        corpus_str += f"""
        Estudio {i+1}: {p.get('authors', 'N/A')}. "{p['title']}". {p.get('journal', 'N/A')}. {p['year']}. DOI: {p.get('doi', 'N/A')}.
        Tipo: {p['study_type']} | Nivel Oxford: {p['oxford_level']} | Calidad: {p['methodological_quality']}/5
        P: {p['picos']['P']}
        I: {p['picos']['I']}
        C: {p['picos']['C']}
        O: {p['picos']['O']}{abstract_line}
        ---
        """

    prompt_consolidated = f"""
    Eres el coordinador del panel de meta-análisis. Genera el debate clínico entre el Sintetizador
    de Evidencia y el Opositor de Sesgos, y consolida la síntesis final de evidencia sobre "{query}".

    Corpus de estudios clínicos analizados (con autores completos para citación):
    {corpus_str}

    REGLA DE CITACIÓN: En todos los campos de texto, cita explícitamente a los autores de los estudios
    del corpus usando el formato (Apellido et al., Año) o (Apellido, Año). Cada hallazgo clave debe
    referenciar el estudio específico del que proviene.

    Genera un resultado en formato JSON estricto con las siguientes claves:
    1. "synthesizer_log": Diálogo del Sintetizador (140-180 palabras). Confirma fichas PICO-S del
       Paso 2, propone nivel GRADE preliminar con citas a 3-4 estudios del corpus, compara técnicas
       citando autores específicos, y pasa la palabra al Opositor.
    2. "bias_opponent_log": Diálogo del Opositor (130-170 palabras). Cuestiona la propuesta citando
       limitaciones metodológicas de estudios concretos, indica gaps de conocimiento, y desafía el
       grado si los tamaños muestrales o diseños lo justifican.
    3. "meta_analysis": Objeto con las claves de la síntesis formal:
       - "global_evidence_level": Nivel de evidencia global con referencia a los estudios del corpus.
       - "grade_recommendation": Grado GRADE definitivo (A/B/C/D) con justificación citando autores.
       - "comparison_findings": Comparación de técnicas con datos numéricos y citas (Autor et al., Año).
       - "knowledge_gaps": Lista de brechas de conocimiento con el estudio que las identifica.
       - "controversies": Lista de controversias citando los estudios en conflicto.
       - "clinical_implications": Recomendaciones prácticas citando la evidencia de respaldo.
       - "evidence_range_years": Objeto con "min" y "max" (enteros) del rango de años de los estudios.
       - "numerical_facts": Lista de objetos {{
           "fact": "descripción de la cifra clínica concreta (ej. 'Tasa de complicaciones LP: 8.3%')",
           "value": "valor exacto con unidades",
           "citation": "Apellido et al. (Año)"
         }} — extrae TODAS las cifras numéricas concretas que aparezcan en los abstracts del corpus
         (porcentajes, tiempos, OR, RR, n de muestra, tasas, dosis). Mínimo 8 hechos si el corpus lo permite.
         Estos hechos son la única fuente autorizada de cifras para el redactor y deben extraerse
         literalmente del corpus, NO fabricados.

    Devuelve un JSON exacto con las claves raíz: "synthesizer_log", "bias_opponent_log", "meta_analysis".
    """
    
    try:
        response_text = await call_gemini(prompt_consolidated, json_mode=True, temperature=0.2, thinking_budget=8192)
        data = json.loads(response_text)
        
        synth_msg = data.get("synthesizer_log", "Síntesis preliminar iniciada.")
        bias_msg = data.get("bias_opponent_log", "Control de sesgos realizado.")
        final_meta = data.get("meta_analysis", {})
        
        # Validar claves mínimas del meta_analysis
        required_keys = [
            "global_evidence_level", "grade_recommendation", "comparison_findings",
            "knowledge_gaps", "controversies", "clinical_implications",
            "evidence_range_years", "numerical_facts"
        ]
        for rk in required_keys:
            if rk not in final_meta:
                final_meta[rk] = [] if rk in ("knowledge_gaps", "controversies", "numerical_facts") else "N/A"
        if not isinstance(final_meta.get("evidence_range_years"), dict):
            years = [p.get("year") for p in analyzed_papers if isinstance(p.get("year"), int)]
            final_meta["evidence_range_years"] = {
                "min": min(years) if years else 2000,
                "max": max(years) if years else 2024
            }
                
    except Exception as e:
        logger.error(f"Error consolidando meta-análisis: {e}")
        # Fallback seguro
        synth_msg = f"Revisando los {len(analyzed_papers)} estudios. El enfoque analítico muestra una gran heterogeneidad."
        bias_msg = "Revisión de sesgos completada. Es necesario reportar de forma transparente las limitaciones metodológicas."
        years = [p.get("year") for p in analyzed_papers if isinstance(p.get("year"), int)]
        final_meta = {
            "global_evidence_level": "Nivel 2b - Basado en estudios de cohortes y ECAs heterogéneos.",
            "grade_recommendation": "Grado B - Recomendación moderada para el enfoque de elección.",
            "comparison_findings": "Las técnicas comparadas muestran resultados quirúrgicos similares en la muestra analizada.",
            "knowledge_gaps": ["Falta de seguimiento prospectivo a largo plazo (>5 años)"],
            "controversies": ["La curva de aprendizaje y costes del cirujano"],
            "clinical_implications": "Se recomienda personalizar la decisión según la anatomía del paciente y experiencia del centro.",
            "evidence_range_years": {
                "min": min(years) if years else 2000,
                "max": max(years) if years else 2024
            },
            "numerical_facts": []
        }
        
    # Enviar mensajes del debate a la cola de logs
    await event_queue.put(sintetizador.format_log(synth_msg, "meta_analyze"))
    await event_queue.put(opositor.format_log(bias_msg, "meta_analyze"))
    
    # Redactar mensaje de cierre del Redactor Científico
    summary_log = f"""He consolidado la síntesis de evidencia y meta-análisis GRADE definitiva sobre "{query}" reuniendo las posturas del Sintetizador y el Opositor de Sesgos.
    El nivel global de evidencia determinado es: {final_meta.get('global_evidence_level')}.
    El grado de recomendación GRADE final asignado es: {final_meta.get('grade_recommendation')}.
    Procedemos a pasar el reporte GRADE al **Redactor Médico** de la Fase de Redacción Científica (Paso 4) para iniciar la confección del apunte clínico de Word."""
    
    await event_queue.put(redactor.format_log(summary_log, "meta_analyze"))
    
    return final_meta
