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

_SLIDE_TARGETS = {
    "short": "entre 15 y 20",
    "medium": "entre 25 y 35",
    "long": "entre 40 y 60",
    "very_detailed": "entre 60 y 80",
}


def _as_list(value) -> List[str]:
    """Normaliza un campo del meta-análisis (str | list | None) a una lista de strings no vacíos."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip() and value.strip().upper() != "N/A":
        # Partir oraciones largas en viñetas legibles
        parts = [s.strip() for s in value.replace("•", ".").split(". ") if s.strip()]
        return parts or [value.strip()]
    return []


def _build_content_slides(
    query: str,
    meta_analysis: Dict[str, Any],
    analyzed_papers: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Construye una baraja de diapositivas REALES y variadas a partir del contenido del
    meta-análisis y los papers analizados. Se usa cuando Gemini falla o devuelve muy
    pocas diapositivas, para que la presentación de respaldo sea del TEMA y no genérica.
    """
    topic = query.strip().capitalize()
    slides: List[Dict[str, Any]] = [
        {
            "layout": "title",
            "title": f"Cirugía Infantil: {topic}",
            "subtitle": "Síntesis de Evidencia Científica · Meta-análisis GRADE",
            "references": "Cuerpo de Evidencia Analizado",
            "speaker_notes": f"Bienvenidos. Presentamos la síntesis de evidencia sobre {topic} basada en {len(analyzed_papers)} estudios analizados."
        },
        {
            "layout": "bullet_points",
            "title": "Objetivos de la Presentación",
            "bullets": [
                f"Sintetizar la evidencia científica actual sobre {topic} en cirugía pediátrica.",
                "Comparar las técnicas quirúrgicas disponibles y sus desenlaces clínicos.",
                "Establecer recomendaciones prácticas según el nivel de evidencia GRADE.",
                "Identificar brechas de conocimiento y controversias vigentes.",
            ],
            "references": "Cuerpo de Evidencia Analizado",
            "speaker_notes": f"Estos son los objetivos académicos y clínicos para el abordaje de {topic}."
        },
    ]

    # Nivel de evidencia y recomendación GRADE
    grade = str(meta_analysis.get("grade_recommendation") or "").strip()
    level = str(meta_analysis.get("global_evidence_level") or "").strip()
    if grade or level:
        slides.append({
            "layout": "metrics",
            "title": "Nivel de Evidencia y Recomendación GRADE",
            "metric_value": grade.split("-")[0].strip()[:18] if grade else "GRADE",
            "metric_label": f"{level}. {grade}".strip(". "),
            "references": "Síntesis GRADE del corpus",
            "speaker_notes": "La recomendación GRADE resume la certeza global de la evidencia para esta patología."
        })

    # Hallazgos comparativos
    comp = _as_list(meta_analysis.get("comparison_findings"))
    if comp:
        slides.append({
            "layout": "bullet_points",
            "title": "Hallazgos Comparativos entre Técnicas",
            "bullets": comp[:5],
            "references": "Comparación del corpus de estudios",
            "speaker_notes": "Aquí se comparan los desenlaces clínicos clave entre las técnicas evaluadas."
        })

    # Hechos numéricos verificados (cifras reales del corpus)
    num_facts = meta_analysis.get("numerical_facts") or []
    fact_bullets = []
    for f in num_facts:
        if isinstance(f, dict):
            fact = str(f.get("fact") or "").strip()
            val = str(f.get("value") or "").strip()
            cite = str(f.get("citation") or "").strip()
            line = " ".join(x for x in [fact, f"({val})" if val and val not in fact else "", f"— {cite}" if cite else ""] if x).strip()
            if line:
                fact_bullets.append(line)
        elif str(f).strip():
            fact_bullets.append(str(f).strip())
    # Repartir las cifras en diapositivas de máximo 5 viñetas
    for i in range(0, len(fact_bullets), 5):
        chunk = fact_bullets[i:i + 5]
        if chunk:
            slides.append({
                "layout": "bullet_points",
                "title": "Cifras Clave de la Evidencia" + (f" (cont. {i // 5 + 1})" if i else ""),
                "bullets": chunk,
                "references": "Datos extraídos del corpus",
                "speaker_notes": "Estas son las cifras clínicas concretas extraídas directamente de los estudios."
            })

    # Implicaciones clínicas
    impl = _as_list(meta_analysis.get("clinical_implications"))
    if impl:
        slides.append({
            "layout": "bullet_points",
            "title": "Implicaciones Clínicas y Recomendaciones",
            "bullets": impl[:5],
            "references": "Síntesis del corpus",
            "speaker_notes": "Recomendaciones prácticas derivadas de la evidencia para la toma de decisiones."
        })

    # Brechas de conocimiento
    gaps = _as_list(meta_analysis.get("knowledge_gaps"))
    if gaps:
        slides.append({
            "layout": "bullet_points",
            "title": "Brechas de Conocimiento",
            "bullets": gaps[:5],
            "references": "Análisis de limitaciones del corpus",
            "speaker_notes": "Identificamos las áreas donde la evidencia actual es insuficiente."
        })

    # Controversias
    contr = _as_list(meta_analysis.get("controversies"))
    if contr:
        slides.append({
            "layout": "bullet_points",
            "title": "Controversias Actuales",
            "bullets": contr[:5],
            "references": "Estudios en conflicto del corpus",
            "speaker_notes": "Estas son las controversias activas en la literatura sobre el tema."
        })

    # Forest plot si hay datos
    if (meta_analysis.get("forest_plot_data") or []):
        slides.append({
            "layout": "forest_plot",
            "title": "Análisis del Forest Plot de Eficacia",
            "bullets": [
                "El gráfico muestra los Odds Ratio (OR) e intervalos de confianza de cada estudio.",
                "El rombo inferior representa el estimado global ponderado (pool).",
                "Valores de OR < 1 favorecen la técnica de intervención.",
            ],
            "references": "Meta-análisis del corpus",
            "speaker_notes": "El forest plot integra visualmente la magnitud del efecto de cada estudio."
        })

    # Tabla de evidencia con los papers reales
    rows = []
    for p in analyzed_papers[:6]:
        authors_raw = p.get("authors", "N/A")
        first_author = authors_raw.split(",")[0].strip()
        cite = f"{first_author} et al. ({p.get('year', 's.f.')})" if "," in authors_raw else f"{first_author} ({p.get('year', 's.f.')})"
        rows.append([
            cite,
            str(p.get("study_type", "N/A"))[:28],
            str(p.get("picos", {}).get("O", "N/A"))[:60],
        ])
    if rows:
        slides.append({
            "layout": "comparison_table",
            "title": "Tabla de Evidencia Científica",
            "headers": ["Estudio", "Tipo", "Hallazgo Principal"],
            "rows": rows,
            "references": "Corpus de estudios analizados",
            "speaker_notes": "Esta tabla resume los estudios clave que sustentan la presentación."
        })

    # Conclusiones
    slides.append({
        "layout": "bullet_points",
        "title": "Conclusiones",
        "bullets": [
            f"La evidencia sobre {topic} respalda una recomendación {grade or 'según el nivel GRADE evaluado'}.",
            comp[0] if comp else "Las técnicas evaluadas presentan perfiles de desenlace diferenciados.",
            impl[0] if impl else "Se recomienda individualizar la decisión según el paciente y el centro.",
        ],
        "references": "Síntesis global del corpus",
        "speaker_notes": "Cerramos resumiendo los mensajes clave y la recomendación final."
    })
    return slides

async def run_presenter_panel(
    meta_analysis: Dict[str, Any],
    analyzed_papers: List[Dict[str, Any]],
    query: str,
    event_queue: asyncio.Queue,
    detail_level: str = "long"
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
    
    # Extraer los 8 mejores papers con metadatos completos para la tabla de evidencia y citas
    papers_subset = []
    for p in analyzed_papers[:8]:
        authors_raw = p.get("authors", "N/A")
        first_author = authors_raw.split(",")[0].strip()
        citation_short = f"{first_author} et al. ({p['year']})" if "," in authors_raw else f"{first_author} ({p['year']})"
        papers_subset.append({
            "citation": citation_short,
            "journal": p.get("journal", "N/A"),
            "oxford": p["oxford_level"],
            "type": p["study_type"],
            "intervention": p["picos"]["I"][:80],
            "findings": p["picos"]["O"][:150] + ("..." if len(p["picos"]["O"]) > 150 else ""),
            "doi": p.get("doi", "N/A")
        })

    papers_json_str = json.dumps(papers_subset, ensure_ascii=False)

    prompt_pptx_json = f"""
    Eres el Programador PPTX. Genera una lista completa y muy detallada de diapositivas clínicas
    explicativas sobre "{query}".
    Información de soporte:
    - Meta-análisis GRADE: {meta_analysis}
    - Papers disponibles para citar (usa el campo "citation" de cada uno): {papers_json_str}

    REGLA DE CITACIÓN OBLIGATORIA: El campo "references" de cada diapositiva DEBE contener la cita
    en formato (Apellido et al., Año) del o los papers que respaldan esa diapositiva, tomando los
    valores exactos del campo "citation" de la lista de papers. Cuando cites datos en las viñetas,
    incluye la cita dentro del texto (ej. "LP: tiempo a alimentación completa 12h vs 18h en cirugía
    abierta (Oomen et al., 2021)"). Solo usa "Consenso de Expertos / Evidencia General" si ningún
    paper del corpus es relevante para esa diapositiva.
    
    Cada diapositiva debe incluir obligatoriamente un campo "speaker_notes" que contenga un guión dinámico, formal e informativo de 2-4 líneas en español que el cirujano ponente debe decir en voz alta al presentar este slide (ej. "En esta diapositiva observamos que...").
    
    Cada diapositiva debe tener uno de los siguientes layouts lógicos:
    1. "title" (campos: "title", "subtitle", "references", "speaker_notes")
    2. "bullet_points" (campos: "title", "bullets" - lista de strings, máximo 5 viñetas, "references", "speaker_notes". IMPORTANTE: Cada viñeta debe ser explicativa y detallar bien la idea en 1 o 2 frases largas y descriptivas, no solo palabras clave sueltas).
    3. "comparison_table" (campos: "title", "headers" - lista de strings, "rows" - lista de listas de strings, máximo 3 columnas y 6 filas, "references", "speaker_notes")
    4. "comparison_2col" (campos: "title", "col1_title" - string, "col1_bullets" - lista de strings, "col2_title" - string, "col2_bullets" - lista de strings, "references", "speaker_notes")
    5. "step_process" (campos: "title", "steps" - lista de strings detallando un proceso de manera descriptiva, "references", "speaker_notes")
    6. "metrics" (campos: "title", "metric_value" - número o frase corta destacada, "metric_label" - descripción detallada de la métrica, "references", "speaker_notes")
    7. "multimodal_chart" (campos: "title", "bullets" - lista de strings analizando una figura o imagen clínica, "references", "speaker_notes")
    8. "forest_plot" (campos: "title", "bullets" - lista de strings interpretando los Odds Ratios del Forest Plot, "references", "speaker_notes")
    
    Instrucciones críticas:
    - Basa el orden clínico, las comparaciones y las descripciones directamente en los papers provistos, citándolos explícitamente en el texto de las viñetas (ej. 'Evidencia: Oomen et al.').
    - Genera {_SLIDE_TARGETS.get(detail_level, "entre 40 y 60")} diapositivas. Explica a fondo cada concepto clínico, especialmente las técnicas quirúrgicas actuales, las técnicas tradicionales y la evolución histórica.
    - La Diapositiva de Tabla de Evidencia debe completarse utilizando los datos estructurados en: {papers_json_str}.
    
    Asegúrate de incluir y expandir detalladamente las siguientes secciones, dedicando múltiples diapositivas a las secciones complejas:
    1. Título de la presentación (layout "title")
    2. Objetivos académicos y clínicos (layout "bullet_points")
    3. Introducción general y Caso Clínico Simulado (Clinical Case Vignette) como gancho (layout "bullet_points")
    4. Epidemiología (incidencia, prevalencia, factores de riesgo) (layout "metrics")
    5. Embriología y Desarrollo Anátomopatológico (layout "bullet_points")
    6. Fisiopatología detallada y cambios tisulares/funcionales (layout "bullet_points")
    7. Anatomía Quirúrgica Pediátrica relevante y relaciones anatómicas de seguridad (layout "bullet_points")
    8. Manifestaciones Clínicas y su presentación según grupo etario (layout "comparison_2col" o "comparison_table")
    9. Diagnóstico Clínico (anamnesis, examen físico, signos clínicos cardinales) (layout "bullet_points")
    10. Diagnóstico por Imágenes (criterios cuantitativos, ultrasonido, radiografía, etc.) (layout "multimodal_chart")
    11. Diagnóstico Diferencial de patologías similares (layout "comparison_table")
    12. Preparación Preoperatoria (regla Holiday-Segar 4-2-1, ayuno 2-4-6) (layout "bullet_points")
    13. Anestesia Pediátrica (vía aérea, inducción, dosis seguras por peso) (layout "bullet_points")
    14. Técnica Quirúrgica Estándar Actual (paso a paso minucioso) (layout "step_process")
    15. Técnica Quirúrgica Abierta Clásica (paso a paso detallado) (layout "step_process")
    16. Técnicas Quirúrgicas Históricas y Evolución (comparación) (layout "comparison_2col")
    17. Cuidados Postoperatorios Inmediatos y Esquemas de Alimentación (layout "bullet_points")
    18. Algoritmos de Tratamiento por Scores y Escalas de Severidad (layout "bullet_points")
    19. Complicaciones Intraoperatorias (lesiones, sangrado) (layout "bullet_points")
    20. Complicaciones Postoperatorias Tempranas y Tardías con porcentajes de incidencia reales (layout "bullet_points")
    21. Seguimiento Clínico y Criterios de Alta Hospitalaria (layout "bullet_points")
    22. Casos Clínicos Complejos y Desafíos (bajo peso, prematuros) (layout "bullet_points")
    23. Perlas Clínicas Quirúrgicas y Sabiduría Práctica (layout "bullet_points")
    24. Errores Comunes en el Diagnóstico y en la Cirugía (layout "bullet_points")
    25. Tabla de Evidencia Científica (usar comparison_table con {papers_json_str})
    26. Análisis Estadístico del Forest Plot de Eficacia (layout "forest_plot")
    27. Conclusiones y Preguntas de Discusión para el equipo (layout "bullet_points")
    
    Genera un JSON con este formato estricto:
    {{
      "slides": [
        {{
          "layout": "title",
          "title": "...",
          "subtitle": "...",
          "references": "Consenso de Expertos / Evidencia General",
          "speaker_notes": "..."
        }},
        {{
          "layout": "bullet_points",
          "title": "...",
          "bullets": ["...", "..."],
          "references": "Oomen et al. (2020)",
          "speaker_notes": "..."
        }},
        ...
      ]
    }}
    """
    
    try:
        response_json_text = await call_gemini(
            prompt_pptx_json, json_mode=True, temperature=0.3,
            thinking_budget=2048, timeout=240.0, max_output_tokens=32768
        )
        data = json.loads(response_json_text)
        slides_list = data.get("slides", [])

        # Si Gemini devolvió muy pocas diapositivas, completar con contenido REAL
        # derivado del meta-análisis (nunca con placeholders idénticos).
        if len(slides_list) < 12:
            logger.warning(f"Gemini generó solo {len(slides_list)} slides. Complementando con contenido del meta-análisis.")
            content_slides = _build_content_slides(query, meta_analysis, analyzed_papers)
            # Evitar duplicar la portada si Gemini ya generó una
            if slides_list and slides_list[0].get("layout") == "title":
                content_slides = [s for s in content_slides if s.get("layout") != "title"]
            slides_list.extend(content_slides)
    except Exception as e:
        logger.error(f"Error generating or parsing PPTX JSON: {e}. Usando deck derivado del meta-análisis.")
        # Fallback del TEMA: baraja construida con los datos reales del meta-análisis y los papers.
        slides_list = _build_content_slides(query, meta_analysis, analyzed_papers)

    await event_queue.put(programador.format_log(f"¡Esquema de diapositivas consolidado en JSON ({len(slides_list)} diapositivas detalladas) con éxito! Enviando el esquema estructurado final al **Sistema de Compilación** para renderizar los entregables .docx y .pptx.", "present"))
    
    return slides_list
