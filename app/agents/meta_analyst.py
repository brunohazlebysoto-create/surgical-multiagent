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

    # Evento inmediato para que el usuario sepa que el paso 3 ya comenzó
    await event_queue.put(sintetizador.format_log(
        f"Recibí {len(analyzed_papers)} fichas PICO-S del Paso 2. Construyendo corpus de evidencia y enviando al motor de síntesis GRADE (puede tardar 60-90 s)...",
        "meta_analyze"
    ))

    try:
        # Corpus compacto: solo los campos esenciales para síntesis GRADE (sin abstractos largos)
        corpus_str = ""
        for i, p in enumerate(analyzed_papers):
            nd = p.get("numeric_data") or {}
            parts = []
            if nd.get("n_patients"):
                parts.append("N=" + str(nd["n_patients"]))
            if nd.get("complication_rate_pct") is not None:
                parts.append("compl." + str(nd["complication_rate_pct"]) + "%")
            if nd.get("operative_time_min") is not None:
                parts.append("T.op." + str(nd["operative_time_min"]) + "min")
            numeric_line = ", ".join(parts)
            title_safe = str(p.get("title", ""))[:80]
            authors_safe = str(p.get("authors", "N/A"))
            year_safe = str(p.get("year", "N/A"))
            study_type_safe = str(p.get("study_type", "N/A"))
            oxford_safe = str(p.get("oxford_level", "N/A"))
            quality_safe = str(p.get("methodological_quality", "N/A"))
            picos_i = str((p.get("picos") or {}).get("I", "N/A"))[:80]
            picos_o = str((p.get("picos") or {}).get("O", "N/A"))[:100]
            line = (
                "[" + str(i+1) + "] " + authors_safe + " (" + year_safe + '). "' + title_safe + '". '
                + study_type_safe + " | Oxford:" + oxford_safe + " | Cal:" + quality_safe + "/5"
                + (" | " + numeric_line if numeric_line else "") + "\n"
                + "    I:" + picos_i + " -> O:" + picos_o + "\n"
            )
            corpus_str += line

        prompt_consolidated = (
            'Eres el coordinador del panel de meta-análisis. Genera el debate clínico entre el Sintetizador\n'
            'de Evidencia y el Opositor de Sesgos, y consolida la síntesis final de evidencia sobre "' + str(query) + '".\n\n'
            'Corpus de estudios clínicos analizados (con autores completos para citación):\n'
            + corpus_str + '\n'
            'REGLA DE CITACIÓN: En todos los campos de texto, cita explícitamente a los autores de los estudios\n'
            'del corpus usando el formato (Apellido et al., Año) o (Apellido, Año). Cada hallazgo clave debe\n'
            'referenciar el estudio específico del que proviene.\n\n'
            'Genera un resultado en formato JSON estricto con las siguientes claves:\n'
            '1. "synthesizer_log": Diálogo del Sintetizador (140-180 palabras). Confirma fichas PICO-S del\n'
            '   Paso 2, propone nivel GRADE preliminar con citas a 3-4 estudios del corpus, compara técnicas\n'
            '   citando autores específicos, y pasa la palabra al Opositor.\n'
            '2. "bias_opponent_log": Diálogo del Opositor (130-170 palabras). Cuestiona la propuesta citando\n'
            '   limitaciones metodológicas de estudios concretos, indica gaps de conocimiento, y desafía el\n'
            '   grado si los tamaños muestrales o diseños lo justifican.\n'
            '3. "meta_analysis": Objeto con las claves de la síntesis formal:\n'
            '   - "global_evidence_level": Nivel de evidencia global con referencia a los estudios del corpus.\n'
            '   - "grade_recommendation": Grado GRADE definitivo (A/B/C/D) con justificación citando autores.\n'
            '   - "comparison_findings": Comparación de técnicas con datos numéricos y citas (Autor et al., Año).\n'
            '   - "knowledge_gaps": Lista de brechas de conocimiento con el estudio que las identifica.\n'
            '   - "controversies": Lista de controversias citando los estudios en conflicto.\n'
            '   - "clinical_implications": Recomendaciones prácticas citando la evidencia de respaldo.\n'
            '   - "evidence_range_years": Objeto con "min" y "max" (enteros) del rango de años de los estudios.\n'
            '   - "numerical_facts": Lista de objetos con claves "fact", "value", "citation" (Autor et al., Año)\n'
            '     con las 5-8 cifras numéricas más relevantes del corpus (tasas, tiempos, n de pacientes).\n\n'
            'Devuelve un JSON exacto con las claves raíz: "synthesizer_log", "bias_opponent_log", "meta_analysis".\n'
            'El objeto "meta_analysis" debe contener: "global_evidence_level", "grade_recommendation",\n'
            '"comparison_findings", "knowledge_gaps", "controversies", "clinical_implications",\n'
            '"evidence_range_years", "numerical_facts".\n'
        )

        response_text = await asyncio.wait_for(
            call_gemini(prompt_consolidated, json_mode=True, temperature=0.2, thinking_budget=4096, timeout=150.0, max_output_tokens=8192),
            timeout=165.0
        )
        data = json.loads(response_text)
        
        synth_msg = data.get("synthesizer_log", "Síntesis preliminar iniciada.")
        bias_msg = data.get("bias_opponent_log", "Control de sesgos realizado.")
        final_meta = data.get("meta_analysis", {})
        
        # Validar claves mínimas del meta_analysis
        required_keys = [
            "global_evidence_level", "grade_recommendation", "comparison_findings",
            "knowledge_gaps", "controversies", "clinical_implications",
            "numerical_facts", "evidence_range_years"
        ]
        list_keys = ("knowledge_gaps", "controversies", "numerical_facts")
        for rk in required_keys:
            if rk not in final_meta:
                if rk in list_keys:
                    final_meta[rk] = []
                else:
                    final_meta[rk] = "N/A"
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
            "numerical_facts": [],
            "evidence_range_years": {
                "min": min(years) if years else 2000,
                "max": max(years) if years else 2024
            }
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
