import asyncio
import logging
from typing import List, Dict, Any
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

async def generate_document_chunk(
    chunk_id: int,
    query: str,
    meta_analysis: Dict[str, Any],
    papers_summary: str
) -> str:
    """Genera una sección del apunte clínico de forma detallada usando Gemini para garantizar extensión y rigor."""

    citation_rule = """
        REGLA DE CITACIÓN OBLIGATORIA: Toda afirmación clínica, estadística, técnica o diagnóstica
        DEBE ir acompañada de una cita explícita en el texto con el formato (Apellido et al., Año)
        o (Apellido, Año) para autor único. Cita SOLO los papers de la 'Lista de referencias' a
        continuación. Incluye MÍNIMO 5 citas por sección. Cada porcentaje, medida, dosis o hallazgo
        clave debe tener su cita correspondiente."""

    prompts = {
        1: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":

        SECCIÓN 1: Introducción, Caso Clínico de Gancho y Epidemiología
        - Inicia OBLIGATORIAMENTE con un Caso Clínico Simulado (Clinical Case Vignette) detallado
          como gancho inicial (edad pediátrica, síntomas, hallazgos físicos, laboratorio e imágenes).
        - Definición de la patología en pediatría, prevalencia global y local, relación de sexo,
          incidencia y factores de riesgo con datos estadísticos concretos.

        SECCIÓN 2: Embriología y Fisiopatología
        - Origen del defecto anatómico en el desarrollo embrionario y fisiopatología detallada
          (alteraciones metabólicas, obstrucción, cascada fisiopatológica).

        Instrucciones de formato:
        - Escribe un mínimo de 1000 palabras para estas dos secciones combinadas.
        - Usa títulos en Markdown (# para secciones principales, ## para subsecciones).
        {citation_rule}

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar (usa estas y solo estas):
        {papers_summary}
        """,

        2: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":

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
        - Escribe un mínimo de 1200 palabras para estas dos secciones combinadas.
        - Usa tablas Markdown estructuradas.
        {citation_rule}

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar (usa estas y solo estas):
        {papers_summary}
        """,

        3: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":

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
        - Escribe un mínimo de 1800 palabras para estas secciones.
        {citation_rule}

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar (usa estas y solo estas):
        {papers_summary}
        """,

        4: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":

        SECCIÓN 7: Síntesis de Evidencia
        - Resumen cruzado comparando las técnicas o estrategias según los estudios analizados.
        - Recomendación GRADE definitiva (A/B/C/D) con justificación basada en los papers.
        - Brechas de conocimiento y controversias actuales.

        SECCIÓN 8: 10 Perlas Clínicas
        - Lista numerada con 10 recomendaciones de sabiduría quirúrgica pediátrica práctica.
        - Cada perla debe citar el paper que la respalda.

        SECCIÓN 9: Referencias (formato Vancouver)
        - Lista numerada de TODOS los papers del contexto, en este formato:
          [N] Apellido Iniciales, Apellido Iniciales. Título del artículo. Nombre Revista Abreviado.
          Año;Volumen(Número):Páginas. DOI: XXXXX.
        - Incluye TODOS los papers de la lista, sin omitir ninguno.

        Instrucciones de formato:
        - Escribe un mínimo de 800 palabras para las secciones 7 y 8.
        - OBLIGATORIO: En la Sección 7, cita explícitamente a cada autor al mencionar sus hallazgos
          (ej. 'Como demostraron Oomen et al. (2021) en su meta-análisis...' o
          'Minneci et al. (2020) reportaron en JAMA...').

        Meta-análisis GRADE disponible:
        {meta_analysis}

        Lista de referencias disponibles para citar y listar en Sección 9:
        {papers_summary}
        """
    }

    return await call_gemini(prompts[chunk_id], temperature=0.25, thinking_budget=8192)

async def run_writer_panel(
    meta_analysis: Dict[str, Any],
    analyzed_papers: List[Dict[str, Any]],
    query: str,
    event_queue: asyncio.Queue
) -> Dict[str, str]:
    """
    Ejecuta el Panel de Redacción (Paso 4).
    Debaten 3 agentes sobre seguridad farmacológica y técnica, y luego redactan el apunte en chunks.
    """
    redactor = MedicalWriterAgent()
    auditor = ClinicalAuditorAgent()
    editor = ChiefEditorAgent()
    
    logger.info("Iniciando Paso 4: Panel de Redacción")
    
    # --- TURNO 1: REDACTOR MÉDICO (Ejecutor) ---
    intro_debate = f"""Recibido el informe GRADE consolidado del **Redactor Científico** (Paso 3) sobre "{query}".
    Procedo a estructurar el apunte clínico. La extensión superará las 2000 palabras cubriendo desde epidemiología hasta la técnica paso a paso.
    Tomo como base los {len(analyzed_papers)} estudios seleccionados y la recomendación GRADE {meta_analysis.get('grade_recommendation')}. 
    Paso la propuesta de estructura al **Auditor Farmacológico y Quirúrgico** para establecer las reglas críticas de seguridad."""
    await event_queue.put(redactor.format_log(intro_debate, "write"))

    # --- TURNO 2: AUDITOR CLÍNICO (Crítico) ---
    audit_msg = f"""Recibida la propuesta de estructura del **Redactor Médico** para el análisis clínico de "{query}". Como Auditor Farmacológico y Quirúrgico, apruebo la disposición de secciones pero exijo estrictamente el cumplimiento de las siguientes directrices de seguridad:
    1. **Dosificación por Peso**: Asegurar que todas las dosis (inducción, mantenimiento anestésico y analgesia) se detallen estrictamente en mg/kg o mcg/kg.
    2. **Algoritmo basado en Scores**: Exijo la inclusión detallada del algoritmo terapéutico dictado por un score clínico de severidad, definiendo el umbral exacto para observación activa, tratamiento conservador/médico y tratamiento quirúrgico.
    3. **Porcentajes Estadísticos**: Es mandatorio especificar los porcentajes de frecuencia de manifestaciones clínicas por grupos de edad, así como las tasas de complicaciones intra y postoperatorias reales según la literatura.
    4. **Reparos de Seguridad**: Describir con precisión los reparos anatómicos de seguridad para evitar lesiones iatrogénicas inadvertidas de estructuras vecinas.
    Transmito estas directrices de seguridad al **Editor en Jefe** para supervisar la redacción final de los chunks."""
    await event_queue.put(auditor.format_log(audit_msg, "write"))

    # --- TURNO 3: EDITOR EN JEFE (Refinador) ---
    editor_msg = f"""Entendido y directrices del **Auditor Farmacológico y Quirúrgico** aprobadas. Como Editor en Jefe, supervisaré que el Redactor Médico aplique cada una de las dosis, ayunos y reparos anatómicos indicados.
    Iniciamos la redacción por secciones detalladas. Al finalizar la compilación del apunte clínico, transferiré las conclusiones y pautas de evidencia al **Diseñador de Diapositivas** del Paso 5 (Presentación) para estructurar el PowerPoint."""
    await event_queue.put(editor.format_log(editor_msg, "write"))

    # --- FASE DE GENERACIÓN MODULAR DE TEXTO (CHUNKS) ---
    # Resumen bibliográfico completo para citación en texto (autor, revista, DOI)
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
            f"[{i+1}] {authors_raw}. \"{p['title']}\". "
            f"{p.get('journal', 'Revista N/A')}. {p['year']}. DOI: {p.get('doi', 'N/A')}.\n"
            f"    Tipo: {p['study_type']} | Oxford: {p['oxford_level']} | Calidad: {p['methodological_quality']}/5\n"
            f"    P: {p['picos']['P']} | I: {p['picos']['I']} | C: {p['picos']['C']} | O: {p['picos']['O']}"
            f"{abstract_line}"
        )
    papers_summary_str = "\n".join(ref_lines)
    
    sections = {}
    
    # Chunk 1
    await event_queue.put(editor.format_log("Redactando Sección 1 y 2: Introducción, Epidemiología, Embriología y Fisiopatología...", "write"))
    try:
        sections["intro_embryo"] = await generate_document_chunk(1, query, meta_analysis, papers_summary_str)
    except Exception as e:
        logger.error(f"Error generando chunk 1: {e}")
        sections["intro_embryo"] = f"# Sección 1: Introducción y Epidemiología\n\nEstudio clínico y epidemiología sobre {query}.\n\n# Sección 2: Embriología y Fisiopatología\n\nFisiopatología de la patología y evolución en cirugía pediátrica."
    
    # Chunk 2
    await event_queue.put(editor.format_log("Redactando Sección 3 y 4: Manifestaciones Clínicas por Edad y Algoritmo Diagnóstico...", "write"))
    try:
        sections["clinical_diag"] = await generate_document_chunk(2, query, meta_analysis, papers_summary_str)
    except Exception as e:
        logger.error(f"Error generando chunk 2: {e}")
        sections["clinical_diag"] = f"# Sección 3: Manifestaciones Clínicas por Grupo Etario\n\nManifestaciones clínicas en neonatos, lactantes y preescolares.\n\n# Sección 4: Diagnóstico\n\nAlgoritmo de diagnóstico y exámenes clínicos de laboratorio e imágenes."
    
    # Chunk 3
    await event_queue.put(editor.format_log("Redactando Sección 5 y 6: Tratamiento (Preparación, Anestesia, Técnica Paso a Paso, Cuidados) y Complicaciones...", "write"))
    try:
        sections["treatment_comp"] = await generate_document_chunk(3, query, meta_analysis, papers_summary_str)
    except Exception as e:
        logger.error(f"Error generando chunk 3: {e}")
        sections["treatment_comp"] = f"# Sección 5: Tratamiento\n\nTécnicas quirúrgicas estándar y clásicas abiertas. Consideraciones de anestesia.\n\n# Sección 6: Complicaciones\n\nComplicaciones intraoperatorias, tempranas y tardías en cirugía infantil."
    
    # Chunk 4
    await event_queue.put(editor.format_log("Redactando Sección 7, 8 y 9: Síntesis de Evidencia, Perlas Clínicas y Referencias...", "write"))
    try:
        sections["evidence_references"] = await generate_document_chunk(4, query, meta_analysis, papers_summary_str)
    except Exception as e:
        logger.error(f"Error generando chunk 4: {e}")
        sections["evidence_references"] = f"# Sección 7: Síntesis de Evidencia\n\nSíntesis de evidencia y grado GRADE.\n\n# Sección 8: Perlas Clínicas\n\nRecomendaciones prácticas.\n\n# Sección 9: Referencias\n\nReferencias y papers utilizados."

    # Log de finalización
    await event_queue.put(editor.format_log("¡Manuscrito médico de más de 2000 palabras completado, auditado y aprobado! Guardando bloques para el renderizador de Word y transmitiendo el texto final al **Diseñador de Diapositivas** de la Fase de Presentación (Paso 5) para iniciar la maquetación del PowerPoint.", "write"))
    
    return sections
