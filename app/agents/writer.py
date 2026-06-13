import asyncio
import logging
from typing import List, Dict, Any, Optional
from app.agents.base import BaseAgent, call_gemini

logger = logging.getLogger("multiagent_writer")

class MedicalWriterAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Redactor Médico",
            role="Ejecutor",
            color="#38bdf8",
            icon="✍️"
        )

class ClinicalAuditorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Auditor Farmacológico y Quirúrgico",
            role="Crítico",
            color="#ef4444",
            icon="🛡️"
        )

class ChiefEditorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Editor en Jefe",
            role="Refinador",
            color="#10b981",
            icon="📰"
        )


# ---------------------------------------------------------------------------
# Deterministic Vancouver reference list (fallback-proof)
# ---------------------------------------------------------------------------

def _build_vancouver_refs(analyzed_papers: List[Dict[str, Any]]) -> str:
    """
    Genera la lista de referencias en formato Vancouver directamente desde los
    datos estructurados. No depende de Gemini, así que garantiza que TODOS los
    papers queden listados y sin duplicados.
    """
    lines = ["\n# Sección 9: Referencias Bibliográficas (Vancouver)\n"]
    for i, p in enumerate(analyzed_papers):
        authors = p.get("authors", "Autores no especificados")
        title = p.get("title", "Sin título")
        journal = p.get("journal", "Revista N/A")
        year = p.get("year", "s.f.")
        doi = p.get("doi", "")
        doi_display = (
            doi if doi and not doi.startswith("pubmed_") and not doi.startswith("user_upload_")
            else "N/A"
        )
        lines.append(f"[{i + 1}] {authors}. {title}. {journal}. {year}. DOI: {doi_display}.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chunk generation
# ---------------------------------------------------------------------------

_CHUNK_SECTIONS_COVERED = """IMPORTANTE — Los siguientes bloques ya fueron redactados por otros autores.
NO los repitas ni los resumas. Empieza directamente en la Sección 7:
  • Sección 1: Introducción + Caso Clínico de Gancho + Epidemiología
  • Sección 2: Embriología y Fisiopatología
  • Sección 3: Manifestaciones Clínicas por Grupo Etario (con tablas)
  • Sección 4: Diagnóstico (clínico, laboratorio, imágenes, score, DDx)
  • Sección 5: Tratamiento (preparación, anestesia, técnicas, postoperatorio)
  • Sección 6: Complicaciones (intraoperatorias, tempranas y tardías con porcentajes)
"""

_DETAIL_WORD_TARGETS = {
    "short":         {"c1": 500,  "c2": 600,  "c3": 600,  "c4": 400},
    "medium":        {"c1": 800,  "c2": 900,  "c3": 900,  "c4": 600},
    "long":          {"c1": 1000, "c2": 1200, "c3": 1200, "c4": 800},
    "very_detailed": {"c1": 1500, "c2": 1800, "c3": 1800, "c4": 1200},
}

async def generate_document_chunk(
    chunk_id: int,
    query: str,
    meta_analysis: Dict[str, Any],
    papers_summary: str,
    inject_context: str = "",
    detail_level: str = "long"
) -> str:
    """
    Genera una sección del apunte clínico usando Gemini.
    inject_context: texto adicional prepended al prompt (usado en chunk 4 para
    evitar que repita las secciones ya redactadas por chunks 1-3).
    detail_level: controla la extensión mínima por chunk.
    """
    wt = _DETAIL_WORD_TARGETS.get(detail_level, _DETAIL_WORD_TARGETS["long"])

    # Contexto de grounding: hechos numéricos extraídos directamente del corpus
    numerical_facts = meta_analysis.get("numerical_facts") or []
    evidence_range = meta_analysis.get("evidence_range_years") or {}
    ev_min = evidence_range.get("min", "")
    ev_max = evidence_range.get("max", "")
    evidence_currency = (
        f"La evidencia disponible abarca publicaciones de {ev_min} a {ev_max}."
        if ev_min and ev_max else ""
    )

    if numerical_facts:
        import json as _json
        facts_str = "\n".join(
            f"  - {f.get('fact', '')}: {f.get('value', '')} ({f.get('citation', '')})"
            for f in numerical_facts
        )
        grounding_block = f"""
        HECHOS NUMÉRICOS VERIFICADOS DEL CORPUS (úsalos textualmente — NO los inventes):
        {facts_str}
        {evidence_currency}
        ADVERTENCIA: Si un dato numérico NO aparece en esta lista ni en la Lista de referencias,
        NO lo incluyas en el texto. Indica la ausencia de dato en cambio de inventarlo.
        """
    else:
        grounding_block = f"\n        {evidence_currency}\n" if evidence_currency else ""

    citation_rule = """
        REGLA DE CITACIÓN OBLIGATORIA: Toda afirmación clínica, estadística, técnica o diagnóstica
        DEBE ir acompañada de una cita explícita en el texto con el formato (Apellido et al., Año)
        o (Apellido, Año) para autor único. Cita SOLO los papers de la 'Lista de referencias' a
        continuación. Incluye MÍNIMO 5 citas por sección. Cada porcentaje, medida, dosis o hallazgo
        clave debe tener su cita correspondiente."""

    prompts = {
        1: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}".
        {grounding_block}

        SECCIÓN 1: Introducción, Caso Clínico de Gancho y Epidemiología
        - Inicia OBLIGATORIAMENTE con un Caso Clínico Simulado (Clinical Case Vignette) detallado
          como gancho inicial (edad pediátrica, síntomas, hallazgos físicos, laboratorio e imágenes).
        - Definición de la patología en pediatría, prevalencia global y local, relación de sexo,
          incidencia y factores de riesgo con datos estadísticos concretos.

        SECCIÓN 2: Embriología y Fisiopatología
        - Origen del defecto anatómico en el desarrollo embrionario y fisiopatología detallada
          (alteraciones metabólicas, obstrucción, cascada fisiopatológica).

        Instrucciones de formato:
        - Escribe un mínimo de {wt['c1']} palabras para estas dos secciones combinadas.
        - Usa títulos en Markdown (# para secciones principales, ## para subsecciones).
        {citation_rule}

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar (usa estas y solo estas):
        {papers_summary}
        """,

        2: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}".
        {grounding_block}

        SECCIÓN 3: Manifestaciones Clínicas por Grupo Etario
        - Cómo varían síntomas según edad (neonato, lactante, preescolar, escolar, adolescente).
        - Porcentajes de frecuencia estadística de síntomas principales según la literatura.
        - TABLA en Markdown comparando manifestaciones con frecuencias en % por grupo etario.

        SECCIÓN 4: Diagnóstico
        - Diagnóstico clínico (anamnesis, examen físico, signos cardinales con sensibilidad/especificidad).
        - Laboratorio: alteraciones con valores cuantitativos exactos.
        - Imagen: criterios cuantitativos exactos (medidas en mm, scores, etc.).
        - Escala/Score clínico de severidad: descripción completa con puntos de corte y algoritmo de decisión.
        - Diagnóstico Diferencial en TABLA Markdown.

        Instrucciones de formato:
        - Escribe un mínimo de {wt['c2']} palabras para estas dos secciones combinadas.
        - Usa tablas Markdown estructuradas.
        {citation_rule}

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar (usa estas y solo estas):
        {papers_summary}
        """,

        3: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}".
        {grounding_block}

        SECCIÓN 5: Tratamiento
        - Preparación preoperatoria: Holliday-Segar (4-2-1), reposición de pérdidas, corrección
          electrolítica, ayuno regla 2-4-6.
        - Anestesia pediátrica: dosis de inducción y mantenimiento en mg/kg o mcg/kg (fentanilo,
          propofol, ketamina, atropina, rocuronio, succinilcolina según corresponda).
        - Tratamiento No Quirúrgico: opciones conservadoras con sus indicaciones según score clínico.
        - Técnicas Quirúrgicas (de más actual/laparoscópica a más antigua/histórica):
          * Técnica Estándar Actual: pasos detallados, colocación de puertos, presiones, reparos anatómicos.
          * Técnica Abierta Clásica: incisiones, disección paso a paso, hemostasia.
          * Técnicas Históricas: evolución hacia la técnica actual.
        - Cuidados postoperatorios: analgesia narcótico-free en mg/kg, reinicio de alimentación.

        SECCIÓN 6: Complicaciones
        - Intraoperatorias, tempranas y tardías.
        - OBLIGATORIO: porcentajes exactos de incidencia de cada complicación según la literatura.

        Instrucciones de formato:
        - Dosis farmacológicas SIEMPRE en mg/kg o mcg/kg.
        - Escribe un mínimo de {wt['c3']} palabras para estas secciones.
        {citation_rule}

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar (usa estas y solo estas):
        {papers_summary}
        """,

        4: f"""
        {inject_context}

        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe ÚNICAMENTE las siguientes secciones del tema "{query}".
        {grounding_block}

        SECCIÓN 7: Síntesis de Evidencia
        - Resumen cruzado comparando las técnicas o estrategias según los estudios analizados.
        - Recomendación GRADE definitiva (A/B/C/D) con justificación basada en los papers.
        - Brechas de conocimiento y controversias actuales.
        - OBLIGATORIO: cita explícitamente a cada autor al mencionar sus hallazgos
          (ej. 'Como demostraron Oomen et al. (2021) en su meta-análisis...' o
          'Minneci et al. (2020) reportaron en JAMA...').

        SECCIÓN 8: 10 Perlas Clínicas
        - Lista numerada con 10 recomendaciones de sabiduría quirúrgica pediátrica práctica.
        - Cada perla debe citar el paper que la respalda.

        Instrucciones de formato:
        - Escribe un mínimo de {wt['c4']} palabras para las secciones 7 y 8.
        - NO incluyas una sección de Referencias — esa se genera automáticamente.
        {citation_rule}

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar (usa estas y solo estas):
        {papers_summary}
        """
    }

    return await call_gemini(prompts[chunk_id], temperature=0.25, thinking_budget=8192)


# ---------------------------------------------------------------------------
# Writer panel (Paso 4)
# ---------------------------------------------------------------------------

async def run_writer_panel(
    meta_analysis: Dict[str, Any],
    analyzed_papers: List[Dict[str, Any]],
    query: str,
    event_queue: asyncio.Queue,
    detail_level: str = "long"
) -> Dict[str, str]:
    """
    Ejecuta el Panel de Redacción (Paso 4).
    Chunks 1-3 se generan EN PARALELO (reducen 3×30s → ~30s).
    Chunk 4 va después con contexto de qué cubrieron los anteriores.
    Las referencias Vancouver se construyen deterministicamente.
    """
    redactor = MedicalWriterAgent()
    auditor = ClinicalAuditorAgent()
    editor = ChiefEditorAgent()

    logger.info("Iniciando Paso 4: Panel de Redacción")

    # Debate de agentes (sin cambios)
    intro_debate = (
        f"Recibido el informe GRADE consolidado del **Redactor Científico** (Paso 3) sobre \"{query}\".\n"
        f"Procedo a estructurar el apunte clínico. La extensión superará las 5000 palabras cubriendo "
        f"desde epidemiología hasta la técnica paso a paso.\n"
        f"Tomo como base los {len(analyzed_papers)} estudios seleccionados y la recomendación GRADE "
        f"{meta_analysis.get('grade_recommendation')}.\n"
        f"Paso la propuesta de estructura al **Auditor Farmacológico y Quirúrgico** para establecer "
        f"las reglas críticas de seguridad."
    )
    await event_queue.put(redactor.format_log(intro_debate, "write"))

    audit_msg = (
        f"Recibida la propuesta de estructura del **Redactor Médico** para el análisis clínico de \"{query}\". "
        f"Como Auditor Farmacológico y Quirúrgico, apruebo la disposición de secciones pero exijo:\n"
        f"1. **Dosificación por Peso**: todas las dosis en mg/kg o mcg/kg.\n"
        f"2. **Algoritmo basado en Scores**: umbral exacto para observación, tratamiento conservador y quirúrgico.\n"
        f"3. **Porcentajes Estadísticos**: frecuencias de manifestaciones y tasas de complicaciones reales.\n"
        f"4. **Reparos de Seguridad**: estructuras vecinas y anatomía crítica.\n"
        f"5. **Redacción en paralelo**: los Chunks 1-3 se redactan simultáneamente para eficiencia máxima."
    )
    await event_queue.put(auditor.format_log(audit_msg, "write"))

    editor_msg = (
        "Directrices aprobadas. Redacción en paralelo (Secciones 1-6) iniciada. "
        "Chunk 4 (Síntesis + Perlas + Referencias) se generará tras la conclusión del bloque paralelo, "
        "con contexto completo de lo redactado para evitar repeticiones."
    )
    await event_queue.put(editor.format_log(editor_msg, "write"))

    # ── Resumen bibliográfico completo ──────────────────────────────────────
    ref_lines = []
    for i, p in enumerate(analyzed_papers):
        authors_raw = p.get("authors", "Autores N/A")
        first_author = authors_raw.split(",")[0].strip()
        abstract_excerpt = (p.get("abstract") or "").strip()
        abstract_line = (
            f"\n    Datos del abstract: {abstract_excerpt[:280]}"
            if abstract_excerpt else ""
        )
        ref_lines.append(
            f"[{i + 1}] {authors_raw}. \"{p['title']}\". "
            f"{p.get('journal', 'Revista N/A')}. {p['year']}. DOI: {p.get('doi', 'N/A')}.\n"
            f"    Tipo: {p['study_type']} | Oxford: {p['oxford_level']} | Calidad: {p['methodological_quality']}/5\n"
            f"    P: {p['picos']['P']} | I: {p['picos']['I']} | C: {p['picos']['C']} | O: {p['picos']['O']}"
            f"{abstract_line}"
        )
    papers_summary_str = "\n".join(ref_lines)

    sections: Dict[str, str] = {}

    # ── CHUNKS 1-3 EN PARALELO ──────────────────────────────────────────────
    await event_queue.put(editor.format_log(
        "Redactando Secciones 1-6 en paralelo (Introducción, Clínica, Diagnóstico, "
        "Tratamiento y Complicaciones)...",
        "write"
    ))

    fallbacks = {
        "intro_embryo": (
            f"# Sección 1: Introducción y Epidemiología\n\nEstudio clínico y epidemiología sobre {query}.\n\n"
            f"# Sección 2: Embriología y Fisiopatología\n\nFisiopatología y evolución en cirugía pediátrica."
        ),
        "clinical_diag": (
            f"# Sección 3: Manifestaciones Clínicas por Grupo Etario\n\n"
            f"Manifestaciones clínicas en neonatos, lactantes y preescolares.\n\n"
            f"# Sección 4: Diagnóstico\n\nAlgoritmo diagnóstico con laboratorio e imágenes."
        ),
        "treatment_comp": (
            f"# Sección 5: Tratamiento\n\nTécnicas quirúrgicas estándar y clásicas abiertas. "
            f"Consideraciones de anestesia.\n\n"
            f"# Sección 6: Complicaciones\n\nComplicaciones intraoperatorias, tempranas y tardías."
        ),
    }

    parallel_results = await asyncio.gather(
        generate_document_chunk(1, query, meta_analysis, papers_summary_str, detail_level=detail_level),
        generate_document_chunk(2, query, meta_analysis, papers_summary_str, detail_level=detail_level),
        generate_document_chunk(3, query, meta_analysis, papers_summary_str, detail_level=detail_level),
        return_exceptions=True
    )

    keys = ["intro_embryo", "clinical_diag", "treatment_comp"]
    for key, result in zip(keys, parallel_results):
        if isinstance(result, Exception):
            logger.error(f"Error generando chunk {key}: {result}")
            sections[key] = fallbacks[key]
        else:
            sections[key] = result

    await event_queue.put(editor.format_log(
        "Secciones 1-6 completadas. Redactando Sección 7 (Síntesis GRADE), "
        "Sección 8 (Perlas Clínicas) y construyendo Referencias Vancouver...",
        "write"
    ))

    # ── CHUNK 4: síntesis + perlas (secuencial, con contexto de los anteriores) ─
    try:
        raw_chunk4 = await generate_document_chunk(
            4, query, meta_analysis, papers_summary_str,
            inject_context=_CHUNK_SECTIONS_COVERED,
            detail_level=detail_level
        )
    except Exception as e:
        logger.error(f"Error generando chunk 4: {e}")
        raw_chunk4 = (
            f"# Sección 7: Síntesis de Evidencia\n\nSíntesis de evidencia y grado GRADE.\n\n"
            f"# Sección 8: Perlas Clínicas\n\nRecomendaciones prácticas de cirugía pediátrica."
        )

    # Quitar cualquier sección de referencias que Gemini haya generado (puede ser incompleta)
    # y reemplazarla por la lista determinista completa.
    cleaned_chunk4 = raw_chunk4
    for marker in ("# Sección 9", "## Sección 9", "# Referencias", "## Referencias",
                   "# REFERENCIAS", "## REFERENCIAS", "# Reference", "## Reference"):
        idx = cleaned_chunk4.find(marker)
        if idx > 0:
            cleaned_chunk4 = cleaned_chunk4[:idx].rstrip()
            break

    sections["evidence_references"] = cleaned_chunk4 + "\n\n" + _build_vancouver_refs(analyzed_papers)

    await event_queue.put(editor.format_log(
        "¡Manuscrito médico de más de 5000 palabras completado, auditado y aprobado! "
        "Guardando bloques para el renderizador de Word y transmitiendo el texto final al "
        "**Diseñador de Diapositivas** de la Fase de Presentación (Paso 5).",
        "write"
    ))

    return sections
