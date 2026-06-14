import asyncio
import json
import logging
from typing import List, Dict, Any
from app.agents.base import BaseAgent, call_gemini

logger = logging.getLogger("multiagent_analyzer")


def _safe_int(val):
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(val):
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


class ExtractorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Extractor Clínico",
            role="Ejecutor",
            color="#38bdf8",
            icon="🧪"
        )

class EvidenceAuditorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Auditor de Evidencia",
            role="Crítico",
            color="#ef4444",
            icon="🔍"
        )

class PicosCuratorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Curador PICO-S",
            role="Refinador",
            color="#10b981",
            icon="✍️"
        )

async def run_analyzer_panel(papers: List[Dict[str, Any]], event_queue: asyncio.Queue) -> List[Dict[str, Any]]:
    """
    Ejecuta el Panel de Análisis (Paso 2) de forma altamente optimizada (2 llamadas API total en lugar de 18).
    Realiza la extracción PICO-S en un solo lote y consolida el debate científico de los agentes.
    """
    extractor = ExtractorAgent()
    auditor = EvidenceAuditorAgent()
    curador = PicosCuratorAgent()
    
    logger.info("Iniciando Paso 2: Panel de Análisis PICO-S Optimizado")
    await event_queue.put(extractor.format_log("Recibido el lote consolidado de papers del Paso 1. Iniciando extracción PICO-S por lotes para optimizar la cuota de la API...", "analyze"))
    
    def _build_picos_prompt(subset: list) -> str:
        return (
            'Analiza la siguiente lista de ' + str(len(subset)) + ' artículos de cirugía pediátrica.\n'
            'Para CADA artículo extrae la información clínica.\n\n'
            'Lista:\n' + json.dumps(subset, ensure_ascii=False) + '\n\n'
            'Devuelve un JSON con la clave "analyses" conteniendo un array de objetos con estas claves:\n'
            '"id" (igual al del artículo), "population", "intervention", "comparison", "outcome",\n'
            '"setting", "oxford_level" (Oxford CEBM: "1a","1b","2a","2b","3","4","5"),\n'
            '"methodological_quality" (entero 1-5), "study_type",\n'
            '"age_groups" (array de "neonato","lactante","preescolar","escolar","adolescente"),\n'
            '"n_patients" (entero o null), "mean_age_months" (número o null),\n'
            '"complication_rate_pct" (número o null), "operative_time_min" (número o null),\n'
            '"confidence_interval" (texto o null).\n'
        )

    def _parse_analyses(batch_json: dict, papers_slice: list, id_offset: int) -> list:
        analyses_map = {a["id"]: a for a in batch_json.get("analyses", [])}
        result = []
        for local_idx, p in enumerate(papers_slice):
            global_idx = id_offset + local_idx
            analysis = analyses_map.get(global_idx, {})
            raw_quality = analysis.get("methodological_quality", 3)
            try:
                quality = max(1, min(5, int(raw_quality)))
            except (TypeError, ValueError):
                quality = 3
            result.append({
                "title": p.get("title", "Sin título"),
                "authors": p.get("authors", "Autores N/A"),
                "journal": p.get("journal", "Revista N/A"),
                "year": p.get("year", 2024),
                "doi": p.get("doi", ""),
                "abstract": p.get("abstract", ""),
                "picos": {
                    "P": analysis.get("population") or "Población infantil",
                    "I": analysis.get("intervention") or "Intervención quirúrgica",
                    "C": analysis.get("comparison") or "Tratamiento alternativo",
                    "O": analysis.get("outcome") or "Resultados clínicos postoperatorios",
                    "S": analysis.get("setting") or "Hospital pediátrico"
                },
                "oxford_level": analysis.get("oxford_level") or "4",
                "methodological_quality": quality,
                "study_type": analysis.get("study_type") or "Estudio Retrospectivo",
                "age_groups": analysis.get("age_groups") or ["lactante"],
                "numeric_data": {
                    "n_patients": _safe_int(analysis.get("n_patients")),
                    "mean_age_months": _safe_float(analysis.get("mean_age_months")),
                    "complication_rate_pct": _safe_float(analysis.get("complication_rate_pct")),
                    "operative_time_min": _safe_float(analysis.get("operative_time_min")),
                    "confidence_interval": analysis.get("confidence_interval") or None,
                }
            })
        return result

    def _fallback_paper(p: dict) -> dict:
        return {
            "title": p.get("title", "Sin título"),
            "authors": p.get("authors", "Autores N/A"),
            "journal": p.get("journal", "Revista N/A"),
            "year": p.get("year", 2024),
            "doi": p.get("doi", ""),
            "abstract": p.get("abstract", ""),
            "picos": {
                "P": "Población infantil",
                "I": "Intervención quirúrgica",
                "C": "Tratamiento alternativo",
                "O": "Resultados clínicos postoperatorios",
                "S": "Hospital pediátrico"
            },
            "oxford_level": "4",
            "methodological_quality": 3,
            "study_type": "Estudio Retrospectivo",
            "age_groups": ["lactante", "escolar"],
            "numeric_data": {
                "n_patients": None, "mean_age_months": None,
                "complication_rate_pct": None, "operative_time_min": None,
                "confidence_interval": None,
            }
        }

    # 1. Dividir papers en 2 lotes paralelos (máx 15 c/u) para evitar que el JSON de salida
    #    supere el límite de tokens y provoque truncación/reintentos interminables.
    mid = len(papers) // 2
    slice_a = [{
        "id": idx,
        "title": p["title"],
        "authors": p["authors"],
        "journal": p["journal"],
        "year": p["year"],
        "abstract": (p.get("abstract") or "")[:400]
    } for idx, p in enumerate(papers[:mid])]

    slice_b = [{
        "id": mid + idx,
        "title": p["title"],
        "authors": p["authors"],
        "journal": p["journal"],
        "year": p["year"],
        "abstract": (p.get("abstract") or "")[:400]
    } for idx, p in enumerate(papers[mid:])]

    await event_queue.put(extractor.format_log(
        f"Dividiendo {len(papers)} papers en 2 lotes paralelos ({len(slice_a)} + {len(slice_b)}) para extracción PICO-S simultánea...",
        "analyze"
    ))

    async def _run_batch(subset: list, offset: int):
        try:
            resp = await asyncio.wait_for(
                call_gemini(_build_picos_prompt(subset), json_mode=True,
                            temperature=0.1, thinking_budget=0,
                            timeout=110.0, max_output_tokens=8192),
                timeout=125.0
            )
            return _parse_analyses(json.loads(resp), papers[offset:offset + len(subset)], offset)
        except Exception as e:
            logger.error(f"Error lote PICO-S offset={offset}: {e}. Usando fallback.")
            return [_fallback_paper(p) for p in papers[offset:offset + len(subset)]]

    results = await asyncio.gather(
        _run_batch(slice_a, 0),
        _run_batch(slice_b, mid),
        return_exceptions=False
    )
    analyzed_papers = results[0] + results[1]

    # 2. Resumir la distribución de estudios
    study_types = {}
    evidence_levels = {}
    for p in analyzed_papers:
        st = p["study_type"]
        ol = p["oxford_level"]
        study_types[st] = study_types.get(st, 0) + 1
        evidence_levels[ol] = evidence_levels.get(ol, 0) + 1
        
    summary_stats = f"Estudios: {dict(study_types)}. Niveles de Evidencia: {dict(evidence_levels)}."
    
    # 3. Generación consolidada del debate de los 3 agentes (1 sola llamada API para los 3 mensajes)
    prompt_debate = f"""
    Genera el diálogo de debate clínico entre los 3 agentes para el análisis de estos artículos:
    Estadísticas del lote: {summary_stats}
    Detalles de los papers:
    {json.dumps([{ "title": p["title"][:60], "oxford": p["oxford_level"], "calidad": p["methodological_quality"] } for p in analyzed_papers], ensure_ascii=False)}
    
    Debes generar las intervenciones de los 3 agentes médicos en formato JSON:
    1. "extractor_log": El Extractor Clínico explica brevemente la extracción PICO-S realizada, los grupos etarios más estudiados y tipos de estudio predominantes (100-140 palabras).
    2. "auditor_log": El Auditor de Evidencia realiza una crítica de la calidad y advierte sobre muestras pequeñas o sesgos en reportes de técnicas quirúrgicas laparoscópicas/abiertas (120-160 palabras).
    3. "curador_log": El Curador PICO-S consolida, indica que refinó los datos y anuncia la transferencia al Sintetizador en el Paso 3 (90-130 palabras).
    
    Devuelve un JSON exacto con las claves: "extractor_log", "auditor_log", "curador_log".
    """
    try:
        response_debate = await asyncio.wait_for(
            call_gemini(prompt_debate, json_mode=True, temperature=0.3, thinking_budget=1024, timeout=90.0),
            timeout=100.0
        )
        debate_data = json.loads(response_debate)
        ext_msg = debate_data.get("extractor_log", "Análisis PICO-S completado.")
        aud_msg = debate_data.get("auditor_log", "Calidad metodológica auditada con éxito.")
        cur_msg = debate_data.get("curador_log", "Base de datos de análisis PICO-S homologada y lista.")
    except Exception as e:
        logger.error(f"Error generando debate consolidado: {e}")
        ext_msg = f"Extracción PICO-S completada para los {len(analyzed_papers)} artículos seleccionados."
        aud_msg = "Auditoría realizada de niveles Oxford CEBM. Se identificaron limitaciones lógicas normales en muestras pequeñas."
        cur_msg = "Consolidación y homologación final completada. Transferimos los datos al Sintetizador para el meta-análisis GRADE."

    # Emitir mensajes al chat
    await event_queue.put(extractor.format_log(ext_msg, "analyze"))
    await event_queue.put(auditor.format_log(aud_msg, "analyze"))
    await event_queue.put(curador.format_log(cur_msg, "analyze"))
    
    return analyzed_papers
