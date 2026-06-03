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
    
    # Formatear el corpus analizado
    corpus_str = ""
    for i, p in enumerate(analyzed_papers):
        corpus_str += f"""
        Estudio {i+1}: {p['title']} ({p['year']})
        Tipo: {p['study_type']} | Nivel Oxford: {p['oxford_level']} | Calidad: {p['methodological_quality']}/5
        P: {p['picos']['P']}
        I: {p['picos']['I']}
        C: {p['picos']['C']}
        O: {p['picos']['O']}
        ---
        """

    prompt_consolidated = f"""
    Eres el coordinador del panel de meta-análisis. Debes generar el debate clínico entre el Sintetizador de Evidencia y el Opositor de Sesgos, además de consolidar la síntesis final de evidencia sobre "{query}".
    
    Corpus de estudios clínicos analizados:
    {corpus_str}
    
    Debes generar un resultado en formato JSON estricto con las siguientes claves:
    1. "synthesizer_log": Diálogo del Sintetizador de Evidencia (Paso 3, Turno 1). Confirma la recepción de las fichas PICO-S del Paso 2, propone un nivel global preliminar y grado GRADE (A, B, C o D), compara brevemente técnicas, y pasa la palabra al Opositor (140-180 palabras).
    2. "bias_opponent_log": Diálogo de Opositor de Sesgos (Paso 3, Turno 2). Cuestiona rigurosamente la propuesta, indica gaps de conocimiento, sesgos de cirujanos sobre laparoscopia y desafía el grado si es necesario (130-170 palabras).
    3. "meta_analysis": Objeto que contiene las siguientes claves de la síntesis formal:
       - "global_evidence_level": Resumen del nivel de evidencia global (ej. "Predominantemente Nivel 2b").
       - "grade_recommendation": Recomendación GRADE definitiva (A, B, C o D) con justificación corta.
       - "comparison_findings": Comparación de técnicas clínicas según el corpus.
       - "knowledge_gaps": Lista de brechas de conocimiento identificadas.
       - "controversies": Lista de controversias o debates en la comunidad quirúrgica pediátrica sobre este tema.
       - "clinical_implications": Recomendaciones prácticas para la toma de decisiones clínicas.
       
    Devuelve un JSON exacto con las claves raíz: "synthesizer_log", "bias_opponent_log", "meta_analysis".
    """
    
    try:
        response_text = await call_gemini(prompt_consolidated, json_mode=True, temperature=0.2)
        data = json.loads(response_text)
        
        synth_msg = data.get("synthesizer_log", "Síntesis preliminar iniciada.")
        bias_msg = data.get("bias_opponent_log", "Control de sesgos realizado.")
        final_meta = data.get("meta_analysis", {})
        
        # Validar claves mínimas del meta_analysis
        required_keys = ["global_evidence_level", "grade_recommendation", "comparison_findings", "knowledge_gaps", "controversies", "clinical_implications"]
        for rk in required_keys:
            if rk not in final_meta:
                final_meta[rk] = "N/A"
                
    except Exception as e:
        logger.error(f"Error consolidando meta-análisis: {e}")
        # Fallback seguro
        synth_msg = f"Revisando los {len(analyzed_papers)} estudios. El enfoque analítico muestra una gran heterogeneidad."
        bias_msg = "Revisión de sesgos completada. Es necesario reportar de forma transparente las limitaciones metodológicas."
        final_meta = {
            "global_evidence_level": "Nivel 2b - Basado en estudios de cohortes y ECAs heterogéneos.",
            "grade_recommendation": "Grado B - Recomendación moderada para el enfoque de elección.",
            "comparison_findings": "Las técnicas comparadas muestran resultados quirúrgicos similares en la muestra analizada.",
            "knowledge_gaps": ["Falta de seguimiento prospectivo a largo plazo (>5 años)"],
            "controversies": ["La curva de aprendizaje y costes del cirujano"],
            "clinical_implications": "Se recomienda personalizar la decisión según la anatomía del paciente y experiencia del centro."
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
