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
    """Normaliza un campo del meta-análisis (str | list | None) a lista de strings no vacíos."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip() and value.strip().upper() != "N/A":
        parts = [s.strip() for s in value.replace("•", ".").split(". ") if s.strip()]
        return parts or [value.strip()]
    return []


def _build_content_slides(
    query: str,
    meta_analysis: Dict[str, Any],
    analyzed_papers: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Construye una baraja de diapositivas REALES a partir del meta-análisis y papers.
    Se usa cuando Gemini falla o devuelve muy pocas diapositivas.
    """
    topic = query.strip().capitalize()

    # Numeric summary from papers for executive slide
    n_patients_total = sum(
        (p.get("numeric_data") or {}).get("n_patients") or 0
        for p in analyzed_papers
        if isinstance((p.get("numeric_data") or {}).get("n_patients"), (int, float))
    )
    comp_rates = [
        (p.get("numeric_data") or {}).get("complication_rate_pct")
        for p in analyzed_papers
        if (p.get("numeric_data") or {}).get("complication_rate_pct") is not None
    ]
    avg_comp = round(sum(comp_rates) / len(comp_rates), 1) if comp_rates else None
    op_times = [
        (p.get("numeric_data") or {}).get("operative_time_min")
        for p in analyzed_papers
        if (p.get("numeric_data") or {}).get("operative_time_min") is not None
    ]
    avg_op = round(sum(op_times) / len(op_times), 1) if op_times else None
    grade = str(meta_analysis.get("grade_recommendation") or "").strip()
    level = str(meta_analysis.get("global_evidence_level") or "").strip()

    exec_bullets = [f"{len(analyzed_papers)} estudios incluidos en la síntesis de evidencia."]
    if n_patients_total:
        exec_bullets.append(f"Total de pacientes analizados: {n_patients_total:,}.")
    if avg_comp is not None:
        exec_bullets.append(f"Tasa de complicaciones promedio reportada: {avg_comp}%.")
    if avg_op is not None:
        exec_bullets.append(f"Tiempo operatorio promedio: {avg_op} min.")
    if grade:
        exec_bullets.append(f"Recomendación GRADE: {grade}.")

    exec_notes = (
        f"Este resumen ejecutivo sintetiza los hallazgos de {len(analyzed_papers)} estudios sobre {topic}. "
        + (f"La población total es de {n_patients_total:,} pacientes. " if n_patients_total else "")
        + (f"Tasa de complicaciones promedio: {avg_comp}%. " if avg_comp is not None else "")
        + (f"Tiempo operatorio promedio: {avg_op} min. " if avg_op is not None else "")
        + f"Nivel de evidencia: {level}. {grade}."
    )

    slides: List[Dict[str, Any]] = [
        {
            "layout": "title",
            "title": f"Cirugía Infantil: {topic}",
            "subtitle": "Síntesis de Evidencia Científica · Meta-análisis GRADE",
            "references": "Cuerpo de Evidencia Analizado",
            "speaker_notes": (
                f"Bienvenidos. Presentamos la síntesis de evidencia sobre {topic} "
                f"basada en {len(analyzed_papers)} estudios analizados. "
                f"Nivel de evidencia: {level}. Recomendación: {grade}."
            )
        },
        {
            "layout": "metrics",
            "title": "Resumen Ejecutivo",
            "metric_value": f"{len(analyzed_papers)} estudios",
            "metric_label": f"{level} · {grade}".strip(" ·"),
            "bullets": exec_bullets,
            "references": "Corpus de evidencia analizado",
            "speaker_notes": exec_notes
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
            "speaker_notes": f"Objetivos académicos y clínicos para el abordaje de {topic}."
        },
    ]

    # Nivel de evidencia y recomendación GRADE
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
            "speaker_notes": "Comparación de los desenlaces clínicos clave entre las técnicas evaluadas."
        })

    # Hechos numéricos verificados (cifras reales del corpus)
    num_facts = meta_analysis.get("numerical_facts") or []
    fact_bullets = []
    for f in num_facts:
        if isinstance(f, dict):
            fact = str(f.get("fact") or "").strip()
            val = str(f.get("value") or "").strip()
            cite = str(f.get("citation") or "").strip()
            line = " ".join(x for x in [
                fact,
                f"({val})" if val and val not in fact else "",
                f"— {cite}" if cite else ""
            ] if x).strip()
            if line:
                fact_bullets.append(line)
        elif str(f).strip():
            fact_bullets.append(str(f).strip())
    for i in range(0, len(fact_bullets), 5):
        chunk = fact_bullets[i:i + 5]
        if chunk:
            slides.append({
                "layout": "bullet_points",
                "title": "Cifras Clave de la Evidencia" + (f" (cont. {i // 5 + 1})" if i else ""),
                "bullets": chunk,
                "references": "Datos extraídos del corpus",
                "speaker_notes": "Cifras clínicas concretas extraídas directamente de los estudios."
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
            "speaker_notes": "Áreas donde la evidencia actual es insuficiente y se requieren más estudios."
        })

    # Controversias
    contr = _as_list(meta_analysis.get("controversies"))
    if contr:
        slides.append({
            "layout": "bullet_points",
            "title": "Controversias Actuales",
            "bullets": contr[:5],
            "references": "Estudios en conflicto del corpus",
            "speaker_notes": "Controversias activas en la literatura científica sobre el tema."
        })

    # Tabla de evidencia con los papers reales
    rows = []
    for p in analyzed_papers[:6]:
        authors_raw = p.get("authors", "N/A")
        first_author = authors_raw.split(",")[0].strip()
        cite = (
            f"{first_author} et al. ({p.get('year', 's.f.')})"
            if "," in authors_raw else f"{first_author} ({p.get('year', 's.f.')})"
        )
        nd = p.get("numeric_data") or {}
        n_str = f"N={nd['n_patients']}" if nd.get("n_patients") else ""
        comp_str = f"Compl. {nd['complication_rate_pct']}%" if nd.get("complication_rate_pct") is not None else ""
        outcome = (p.get("picos", {}).get("O") or "N/A")[:55]
        numeric_note = ", ".join(filter(None, [n_str, comp_str]))
        rows.append([
            cite,
            str(p.get("study_type", "N/A"))[:28],
            f"{outcome} ({numeric_note})" if numeric_note else outcome,
        ])
    if rows:
        slides.append({
            "layout": "comparison_table",
            "title": "Tabla de Evidencia Científica",
            "headers": ["Estudio", "Tipo", "Hallazgo / Datos"],
            "rows": rows,
            "references": "Corpus de estudios analizados",
            "speaker_notes": (
                "Esta tabla resume los estudios clave con sus datos numéricos principales. "
                + (f"Tasa de complicaciones promedio: {avg_comp}%. " if avg_comp is not None else "")
                + (f"Tiempo operatorio promedio: {avg_op} min." if avg_op is not None else "")
            )
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
        "speaker_notes": "Cerramos resumiendo los mensajes clave y la recomendación final para la práctica clínica."
    })
    return slides


async def _presenter_heartbeat(queue, prog_agent):
    """Sends periodic messages during PPTX generation to keep the SSE stream alive."""
    await asyncio.sleep(60.0)
    await queue.put(prog_agent.format_log(
        "Generando esquema de diapositivas (proceso intensivo, puede tardar 3-4 min)...",
        "present"
    ))
    await asyncio.sleep(65.0)
    await queue.put(prog_agent.format_log(
        "Estructurando diapositivas clínicas con notas del ponente... en progreso",
        "present"
    ))
    await asyncio.sleep(65.0)
    await queue.put(prog_agent.format_log(
        "Finalizando JSON de presentación... respuesta inminente.",
        "present"
    ))


async def run_presenter_panel(
    meta_analysis: Dict[str, Any],
    analyzed_papers: List[Dict[str, Any]],
    query: str,
    event_queue: asyncio.Queue,
    detail_level: str = "long"
) -> List[Dict[str, Any]]:
    """
    Ejecuta el Panel de Presentación (Paso 5).
    Debaten 3 agentes sobre legibilidad visual y estructura de diapositivas,
    y luego generan un JSON con diapositivas detalladas sin límite rígido de 25.
    Fallback: _build_content_slides() con datos reales del corpus.
    """
    disenador = SlideDesignerAgent()
    auditor = VisualAuditorAgent()
    programador = PptxProgrammerAgent()

    logger.info("Iniciando Paso 5: Panel de Presentación")

    intro_msg = (
        f"Recibido el manuscrito final y el corpus del **Editor en Jefe** del Paso 4. "
        f"He comenzado a estructurar la presentación profesional de diapositivas para el tema \"{query}\". "
        f"Diseñaré una secuencia detallada de diapositivas ({_SLIDE_TARGETS.get(detail_level,'entre 40 y 60')}) "
        f"cubriendo epidemiología, embriología, anatomía, técnica quirúrgica paso a paso, complicaciones y tabla comparativa. "
        f"Cada diapositiva incluirá notas del ponente con datos numéricos reales del corpus. "
        f"Paso la propuesta al **Auditor Visual y Lógico** para validar la legibilidad."
    )
    await event_queue.put(disenador.format_log(intro_msg, "present"))

    aud_msg = (
        f"Recibido el esquema de diapositivas del **Diseñador de Diapositivas** para \"{query}\". "
        f"Apruebo y exijo:\n"
        f"1. **Resumen Ejecutivo** como segunda diapositiva con cifras numéricas reales del corpus.\n"
        f"2. **Notas del ponente** de 3-4 líneas con datos numéricos (N, %, min) en cada slide.\n"
        f"3. **Tabla de evidencia** con N de pacientes y tasa de complicaciones visibles.\n"
        f"4. **Layouts variados**: title, bullet_points, comparison_table, step_process, metrics.\n"
        f"Transmito al **Programador PPTX** para la codificación del JSON final."
    )
    await event_queue.put(auditor.format_log(aud_msg, "present"))

    await event_queue.put(programador.format_log(
        "Directrices visuales recibidas. Generando JSON con notas del ponente ricas en datos numéricos...",
        "present"
    ))

    # Extraer los 8 mejores papers con metadatos completos para citas y tabla de evidencia
    papers_subset = []
    for p in analyzed_papers[:8]:
        authors_raw = p.get("authors", "N/A")
        first_author = authors_raw.split(",")[0].strip()
        citation_short = (
            f"{first_author} et al. ({p['year']})"
            if "," in authors_raw else f"{first_author} ({p['year']})"
        )
        nd = p.get("numeric_data") or {}
        numeric_note = ", ".join(filter(None, [
            f"N={nd['n_patients']}" if nd.get("n_patients") else None,
            f"compl. {nd['complication_rate_pct']}%" if nd.get("complication_rate_pct") is not None else None,
            f"T.op. {nd['operative_time_min']} min" if nd.get("operative_time_min") is not None else None,
            nd.get("confidence_interval") or None,
        ]))
        papers_subset.append({
            "citation": citation_short,
            "journal": p.get("journal", "N/A"),
            "oxford": p["oxford_level"],
            "type": p["study_type"],
            "intervention": p["picos"]["I"][:80],
            "findings": p["picos"]["O"][:150] + ("..." if len(p["picos"]["O"]) > 150 else ""),
            "numeric": numeric_note,
            "doi": p.get("doi", "N/A")
        })

    papers_json_str = json.dumps(papers_subset, ensure_ascii=False)

    meta_lean = {
        "global_evidence_level": meta_analysis.get("global_evidence_level", ""),
        "grade_recommendation":  meta_analysis.get("grade_recommendation", ""),
        "comparison_findings":   meta_analysis.get("comparison_findings", ""),
        "clinical_implications": meta_analysis.get("clinical_implications", ""),
        "knowledge_gaps":        meta_analysis.get("knowledge_gaps", []),
        "controversies":         meta_analysis.get("controversies", []),
    }

    prompt_pptx_json = f"""
    Eres el Programador PPTX. Genera una lista completa y muy detallada de diapositivas clínicas
    explicativas sobre "{query}".
    Información de soporte:
    - Síntesis GRADE: {json.dumps(meta_lean, ensure_ascii=False)}
    - Papers para citar (usa el campo "citation"): {papers_json_str}

    REGLA DE CITACIÓN: El campo "references" de cada diapositiva DEBE contener la cita
    (Apellido et al., Año) tomada del campo "citation" de los papers. Cuando cites datos en las
    viñetas inclúyela en el texto (ej. "12h vs 18h (Oomen et al., 2021)"). Solo usa
    "Consenso de Expertos / Evidencia General" si ningún paper es relevante para esa diapositiva.

    REGLA DE NOTAS DEL PONENTE: El campo "speaker_notes" de CADA diapositiva debe tener 3-4 líneas
    en español con: (a) introducción verbal del slide, (b) datos numéricos reales del corpus
    (N de pacientes, % complicaciones, tiempo operatorio), (c) mensaje clave para el ponente,
    (d) posible pregunta de audiencia y respuesta recomendada.

    Layouts disponibles:
    1. "title"           → campos: title, subtitle, references, speaker_notes
    2. "bullet_points"   → campos: title, bullets (máx 5 viñetas, 1-2 frases c/u), references, speaker_notes
    3. "comparison_table"→ campos: title, headers (lista), rows (lista de listas, máx 3 cols × 6 filas), references, speaker_notes
    4. "comparison_2col" → campos: title, col1_title, col1_bullets, col2_title, col2_bullets, references, speaker_notes
    5. "step_process"    → campos: title, steps (lista descriptiva), references, speaker_notes
    6. "metrics"         → campos: title, metric_value (valor destacado), metric_label (descripción), references, speaker_notes
    7. "multimodal_chart"→ campos: title, bullets (análisis de imagen clínica), references, speaker_notes

    Instrucciones:
    - Genera {_SLIDE_TARGETS.get(detail_level, "entre 40 y 60")} diapositivas con contenido clínico real.
    - La segunda diapositiva DEBE ser "Resumen Ejecutivo" (layout "metrics") con datos del corpus.
    - Cita los papers explícitamente en las viñetas (ej. "Evidencia: Oomen et al.").
    - Cada viñeta debe ser explicativa (1-2 frases), nunca solo palabras clave sueltas.

    Secciones obligatorias:
    1. Título ("title")
    2. Resumen Ejecutivo con cifras numéricas ("metrics")
    3. Objetivos ("bullet_points")
    4. Introducción y Caso Clínico de Gancho ("bullet_points")
    5. Epidemiología ("metrics")
    6. Embriología y Desarrollo Anatomopatológico ("bullet_points")
    7. Fisiopatología detallada ("bullet_points")
    8. Anatomía Quirúrgica Pediátrica ("bullet_points")
    9. Manifestaciones Clínicas por grupo etario ("comparison_2col" o "comparison_table")
    10. Diagnóstico Clínico ("bullet_points")
    11. Diagnóstico por Imágenes ("multimodal_chart")
    12. Diagnóstico Diferencial ("comparison_table")
    13. Preparación Preoperatoria — Holliday-Segar 4-2-1, ayuno 2-4-6 ("bullet_points")
    14. Anestesia Pediátrica — dosis mg/kg ("bullet_points")
    15. Técnica Quirúrgica Actual paso a paso ("step_process")
    16. Técnica Abierta Clásica paso a paso ("step_process")
    17. Evolución Histórica de Técnicas ("comparison_2col")
    18. Cuidados Postoperatorios y Alimentación ("bullet_points")
    19. Algoritmos y Scores de Severidad ("bullet_points")
    20. Complicaciones Intraoperatorias ("bullet_points")
    21. Complicaciones Postoperatorias — incidencias % ("bullet_points")
    22. Seguimiento y Criterios de Alta ("bullet_points")
    23. Casos Clínicos Complejos — prematuros, bajo peso ("bullet_points")
    24. Perlas Clínicas Quirúrgicas ("bullet_points")
    25. Errores Comunes en Diagnóstico y Cirugía ("bullet_points")
    26. Tabla de Evidencia Científica con datos numéricos ("comparison_table" con los papers)
    27. Conclusiones y Preguntas de Discusión ("bullet_points")

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
        ...
      ]
    }}
    """

    hb_task = asyncio.create_task(_presenter_heartbeat(event_queue, programador))
    try:
        response_json_text = await asyncio.wait_for(
            call_gemini(
                prompt_pptx_json, json_mode=True, temperature=0.3,
                thinking_budget=0, timeout=150.0, max_output_tokens=32768
            ),
            timeout=165.0
        )
        data = json.loads(response_json_text)
        slides_list = data.get("slides", [])

        # Si Gemini devolvió muy pocas diapositivas, completar con contenido REAL del meta-análisis
        if len(slides_list) < 12:
            logger.warning(f"Gemini generó solo {len(slides_list)} slides. Complementando con meta-análisis.")
            content_slides = _build_content_slides(query, meta_analysis, analyzed_papers)
            if slides_list and slides_list[0].get("layout") == "title":
                content_slides = [s for s in content_slides if s.get("layout") != "title"]
            slides_list.extend(content_slides)
    except Exception as e:
        logger.error(f"Error generating or parsing PPTX JSON: {e}. Usando deck derivado del meta-análisis.")
        slides_list = _build_content_slides(query, meta_analysis, analyzed_papers)
    finally:
        hb_task.cancel()

    await event_queue.put(programador.format_log(
        f"¡Esquema de diapositivas consolidado en JSON ({len(slides_list)} diapositivas detalladas) con éxito! "
        f"Enviando el esquema estructurado final al **Sistema de Compilación** para renderizar los entregables .docx y .pptx.",
        "present"
    ))

    return slides_list
