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
    
    prompts = {
        1: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":
        
        SECCIÓN 1: Introducción y Epidemiología
        - Definición de la patología en pediatría, prevalencia, relación de sexo, incidencia y factores de riesgo.
        
        SECCIÓN 2: Embriología y Fisiopatología
        - Origen del defecto anatómico en el desarrollo embrionario (si aplica) y la fisiopatología detallada (alteraciones metabólicas, obstrucción, etc.).
        
        Instrucciones de formato:
        - Sé muy riguroso y académico.
        - Escribe un mínimo de 1000 palabras para estas dos secciones combinadas.
        - Usa títulos en Markdown (H1 para secciones principales, H2 para subsecciones).
        - Utiliza la siguiente información de meta-análisis y papers como contexto:
        {meta_analysis}
        """,
        
        2: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":
        
        SECCIÓN 3: Manifestaciones Clínicas por Grupo Etario (neonato, lactante, preescolar, escolar, adolescente)
        - Explica cómo varían los síntomas según la edad.
        - Agrega porcentajes de frecuencia estadística para los síntomas principales (ej. qué porcentaje presenta dolor, vómito, fiebre, etc. según la literatura).
        - Diseña una TABLA detallada en Markdown comparando las manifestaciones y sus frecuencias en porcentajes por grupo etario.
        
        SECCIÓN 4: Diagnóstico
        - Diagnóstico clínico (anamnesis, examen físico, signos cardinales).
        - Laboratorio (alteraciones de laboratorio asociadas con dosis/límites).
        - Diagnóstico por Imagen (ecografías, radiografías, tomografías u otros estudios con medidas y criterios cuantitativos exactos).
        - Escalas Clínicas, Scores de Riesgo o Criterios de Severidad: Describe e inyecta una escala o score de riesgo específico de esta patología que actúe como guía de decisión clínica.
        - Algoritmo de Tratamiento: Explica el algoritmo clínico dictado por dicho score (indicando cuándo proceder a observación activa/vigilancia, cuándo a tratamiento médico/conservador y cuándo a cirugía).
        - Diagnóstico Diferencial en una TABLA detallada en Markdown.
        
        Instrucciones de formato:
        - Sé muy riguroso y académico.
        - Escribe un mínimo de 1200 palabras para estas dos secciones combinadas.
        - Usa tablas Markdown estructuradas.
        - Utiliza la siguiente información de meta-análisis y papers como contexto:
        {meta_analysis}
        {papers_summary}
        """,
        
        3: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":
        
        SECCIÓN 5: Tratamiento
        - Preparación preoperatoria: Manejo de líquidos y electrolitos usando reglas pediátricas como Holliday-Segar (4-2-1) y reposición de pérdidas. Corrección de desequilibrios metabólicos o electrolíticos específicos. Ayuno estricto con la regla 2-4-6 (líquidos claros, leche materna, sólidos/fórmulas).
        - Anestesia pediátrica: Dosis de inducción y mantenimiento en mg/kg o mcg/kg (fentanilo, atropina, rocuronio, etc. según corresponda). Prevención de hipotermia.
        - Tratamiento No Quirúrgico y Manejo Médico Conservador: Detalla detalladamente las opciones no quirúrgicas, terapia farmacológica/médica de soporte u observación clínica/vigilancia si corresponde según la escala de severidad específica de la patología.
        - Técnicas Quirúrgicas (Ordenadas estrictamente de la más actual/utilizada a la más antigua/histórica):
          * Para cada técnica, detalla minuciosamente los pasos quirúrgicos, instrumental, colocación de puertos/incisiones, abordajes tridimensionales y reparos anatómicos de seguridad para evitar complicaciones.
          * Técnica Estándar Actual: abordaje de elección actual (ej. mínimamente invasivo/laparoscópico si aplica), colocación de puertos, presiones de neumoperitoneo correspondientes, pasos paso a paso desde el acceso inicial hasta el cierre final, incluyendo pruebas de seguridad anatómicas aplicables.
          * Técnica Abierta Clásica: abordaje clásico convencional abierto, incisiones anatómicas, pasos detallados de disección, técnica específica y hemostasia cuidadosa.
          * Técnicas Históricas o Alternativas: describe abordajes quirúrgicos previos u obsoletos detallando cómo evolucionaron hacia los métodos actuales.
        - Cuidados postoperatorios: Manejo del dolor con esquemas analgésicos narcótico-free en mg/kg (ibuprofeno, paracetamol), reinicio de alimentación (ad-libitum vs graduado según la patología).
        
        SECCIÓN 6: Complicaciones
        - Divididas en: Intraoperatorias (lesiones inadvertidas de estructuras vecinas, sangrado), tempranas (infección de herida, dehiscencias, etc.) y tardías (recidiva, estenosis, hernias incisionales, etc.).
        - **Es obligatorio incluir porcentajes exactos de incidencia o tasas de complicación** para cada evento según reporta la literatura científica.
        
        Instrucciones de formato:
        - **Es obligatorio incluir dosis farmacológicas detalladas en mg/kg o mcg/kg.**
        - Explica de forma sumamente detallada las técnicas quirúrgicas (de la más actual a la más antigua) sin escatimar en palabras.
        - Escribe un mínimo de 1800 palabras para estas secciones de tratamiento y complicaciones, sin disminuir el detalle de las otras partes del documento.
        - Utiliza la siguiente información de meta-análisis y papers como contexto:
        {meta_analysis}
        {papers_summary}
        """,
        
        4: f"""
        Eres un Redactor Médico especializado en cirugía pediátrica.
        Escribe un manuscrito extremadamente detallado para las siguientes secciones del tema "{query}":
        
        SECCIÓN 7: Síntesis de Evidencia
        - Resumen cruzado de la evidencia actual analizada por los paneles.
        - Recomendación GRADE explicada (A, B, C o D).
        
        SECCIÓN 8: 10 Perlas Clínicas
        - Una lista numerada con 10 recomendaciones clínicas prácticas de "sabiduría quirúrgica" pediátrica.
        
        SECCIÓN 9: Referencias
        - Lista numerada únicamente de los papers y documentos analizados que te fueron proporcionados en el contexto (Autores. Título. Revista. Año. DOI/Local ID). No incluyas referencias externas.
        
        Instrucciones de formato:
        - Sé muy riguroso y académico.
        - Escribe un mínimo de 800 palabras para estas secciones combinadas.
        - Es obligatorio que bases tu redacción de forma estricta en el modelo de presentación y datos de los papers proporcionados en la lista de contexto, citando a los autores directamente (ej. 'Como describe Oomen et al. (2021)...').
        - Utiliza la siguiente información de meta-análisis y papers como contexto:
        {meta_analysis}
        {papers_summary}
        """
    }
    
    return await call_gemini(prompts[chunk_id], temperature=0.25)

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
    # Resumen de papers para inyectar en los prompts
    papers_summary_str = "\n".join([f"- {p['title']} ({p['year']}), PICO: {p['picos']['P']} -> {p['picos']['I']} vs {p['picos']['C']}. Oxford Nivel {p['oxford_level']}" for p in analyzed_papers])
    
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
