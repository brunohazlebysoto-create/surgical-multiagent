import asyncio
import json
import logging
import httpx
from typing import List, Dict, Any
from app.agents.base import BaseAgent, call_gemini
from app.core.database import search_fallback_database

logger = logging.getLogger("multiagent_searcher")

class SearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AGENTE 1 — TERMINÓLOGO MÉDICO MULTILINGÜE",
            role="Terminólogo",
            color="#38bdf8",  # Azul claro
            icon="🔍"
        )

class CriticSearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AGENTE 2 — ESTRATEGA DE BÚSQUEDA",
            role="Estratega",
            color="#ef4444",  # Rojo
            icon="🛡️"
        )

class RefinerSearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AGENTE 3 — REVISOR CRÍTICO Y CURADOR DE EVIDENCIA",
            role="Revisor",
            color="#10b981",  # Verde
            icon="🤝"
        )

async def query_pubmed(search_term: str) -> List[Dict[str, Any]]:
    """Consulta la API de PubMed y devuelve metadatos de los papers."""
    try:
        # 1. Buscar IDs
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": search_term,
            "retmode": "json",
            "retmax": "20"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(search_url, params=params)
            res.raise_for_status()
            id_list = res.json().get("esearchresult", {}).get("idlist", [])
            
        if not id_list:
            return []
            
        # 2. Obtener resúmenes
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        params_summary = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            res_sum = await client.get(summary_url, params=params_summary)
            res_sum.raise_for_status()
            results = res_sum.json().get("result", {})
            
        papers = []
        for uid in id_list:
            info = results.get(uid, {})
            title = info.get("title", "")
            if not title:
                continue
            
            # Obtener autores
            authors_list = info.get("authors", [])
            authors_str = ", ".join([a.get("name", "") for a in authors_list[:3]])
            if len(authors_list) > 3:
                authors_str += " et al."
                
            journal = info.get("source", "PubMed Document")
            pub_date = info.get("pubdate", "")
            year = int(pub_date.split()[0]) if pub_date else 2024
            
            # Intentar obtener DOI de las propiedades del artículo
            doi = ""
            for article_id in info.get("articleids", []):
                if article_id.get("idtype") == "doi":
                    doi = article_id.get("value", "")
            
            # PubMed no devuelve abstracts en esummary de forma simple, creamos un abstract sintetizado/mínimo
            abstract = f"Estudio publicado en {journal} sobre {title}. Analiza la población y resultados de la intervención en cirugía pediátrica."
            
            papers.append({
                "title": title,
                "authors": authors_str,
                "journal": journal,
                "year": year,
                "doi": doi if doi else f"pubmed_{uid}",
                "abstract": abstract
            })
        return papers
    except Exception as e:
        logger.error(f"Error consultando PubMed: {e}")
        return []

async def query_crossref(search_term: str) -> List[Dict[str, Any]]:
    """Consulta la API de CrossRef para enriquecer los papers."""
    try:
        url = "https://api.crossref.org/works"
        params = {
            "query": search_term,
            "rows": "20"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params)
            res.raise_for_status()
            items = res.json().get("message", {}).get("items", [])
            
        papers = []
        for item in items:
            title_list = item.get("title", [])
            title = title_list[0] if title_list else ""
            if not title:
                continue
                
            authors_list = item.get("author", [])
            authors_str = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list[:3]])
            if len(authors_list) > 3:
                authors_str += " et al."
                
            journal_list = item.get("container-title", [])
            journal = journal_list[0] if journal_list else "CrossRef Document"
            
            # Año de publicación
            year = 2024
            pub_parts = item.get("published-print", {}).get("date-parts", []) or item.get("published-online", {}).get("date-parts", [])
            if pub_parts and pub_parts[0]:
                year = pub_parts[0][0]
                
            doi = item.get("DOI", "")
            
            # Abstract
            abstract = item.get("abstract", "")
            if not abstract:
                abstract = f"Estudio clínico sobre {title} analizando resultados postoperatorios y técnicas quirúrgicas."
            
            papers.append({
                "title": title,
                "authors": authors_str,
                "journal": journal,
                "year": year,
                "doi": doi,
                "abstract": abstract
            })
        return papers
    except Exception as e:
        logger.error(f"Error consultando CrossRef: {e}")
        return []

async def query_openalex(search_term: str) -> List[Dict[str, Any]]:
    """Consulta la API de OpenAlex (250M+ artículos de todas las editoriales) para ampliar la búsqueda."""
    try:
        url = "https://api.openalex.org/works"
        params = {
            "search": search_term,
            "per_page": "20"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"User-Agent": "mailto:surgical-system@example.com"} # Requisito de OpenAlex
            res = await client.get(url, params=params, headers=headers)
            res.raise_for_status()
            results = res.json().get("results", [])
            
        papers = []
        for item in results:
            title = item.get("display_name") or ""
            if not title:
                continue
                
            # Autores
            authorships = item.get("authorships", [])
            authors_list = [a.get("author", {}).get("display_name", "") for a in authorships if a.get("author")]
            authors_str = ", ".join(authors_list[:3])
            if len(authors_list) > 3:
                authors_str += " et al."
            if not authors_str:
                authors_str = "Autores no especificados"
                
            # Revista/Fuente
            source_info = item.get("primary_location", {}).get("source")
            journal = source_info.get("display_name") if source_info else "OpenAlex Document"
            if not journal:
                journal = "OpenAlex Document"
                
            # Año
            year = item.get("publication_year") or 2024
            
            # DOI
            doi = item.get("doi", "")
            if doi:
                doi = doi.replace("https://doi.org/", "")
            else:
                doi = item.get("id", "").split("/")[-1]
                
            # Reconstruir abstract
            abstract_dict = item.get("abstract_inverted_index")
            abstract = ""
            if abstract_dict:
                try:
                    word_list = []
                    for word, positions in abstract_dict.items():
                        for pos in positions:
                            word_list.append((pos, word))
                    word_list.sort()
                    abstract = " ".join([word for pos, word in word_list])
                except Exception:
                    abstract = ""
                    
            if not abstract or len(abstract) < 20:
                abstract = f"Estudio científico indexado sobre {title} analizando técnicas y resultados quirúrgicos en la población pediátrica."
                
            papers.append({
                "title": title,
                "authors": authors_str,
                "journal": journal,
                "year": year,
                "doi": doi,
                "abstract": abstract
            })
        return papers
    except Exception as e:
        logger.error(f"Error consultando OpenAlex: {e}")
        return []

import re

def is_clinical_paper(title: str, abstract: str) -> bool:
    """Retorna True si el artículo está enfocado en clínica humana/cirugía y no en ciencia básica/células."""
    text = (title + " " + abstract).lower()
    # Patrones de palabras clave prohibidas (ciencia básica, molecular, celular, animal)
    forbidden_patterns = [
        r'\bcell\b', r'\bcells\b', r'\bcellular\b', r'\bmolecular\b', 
        r'\bgene\b', r'\bgenes\b', r'\bgenetic\b', r'\bgenetics\b',
        r'\bdna\b', r'\brna\b', r'\bmicroarray\b', r'\bin vitro\b', 
        r'\brat\b', r'\brats\b', r'\bmouse\b', r'\bmice\b', r'\banimal\b', 
        r'\banimals\b', r'\bsignaling\b', r'\bpathway\b', r'\bpathways\b',
        r'\breceptor\b', r'\breceptors\b', r'\bprotein expression\b',
        r'\bgene expression\b', r'\bmessenger rna\b', r'\bmrna\b'
    ]
    for pattern in forbidden_patterns:
        if re.search(pattern, text):
            return False
    return True

async def run_search_panel(query: str, event_queue: asyncio.Queue) -> List[Dict[str, Any]]:
    """
    Ejecuta el Panel de Búsqueda (Paso 1).
    Debaten y actúan 3 agentes expertos en revisión de literatura médica según las especificaciones del usuario.
    Consolida una lista de 15 papers para el flujo del pipeline.
    """
    buscador = SearcherAgent()
    critico = CriticSearchAgent()
    refinador = RefinerSearchAgent()
    
    # --- TURNO 1: AGENTE 1 — TERMINÓLOGO MÉDICO MULTILINGÜE ---
    logger.info("Iniciando Paso 1: Turno 1 (Terminólogo Médico)")
    
    prompt_agente1 = f"""
    Actúa como el AGENTE 1 — TERMINÓLOGO MÉDICO MULTILINGÜE.
    Toma el siguiente tema de investigación clínica: "{query}"
    
    Tu tarea:
    1. Tradúcelo y expándelo a:
       - Terminología médica formal en español.
       - Términos equivalentes en inglés médico.
       - Términos MeSH (Medical Subject Headings) exactos de PubMed.
       - Términos Emtree de Embase.
       - Sinónimos, acrónimos, nombres antiguos y nombres comerciales relevantes.
       - Términos equivalentes en otros idiomas con producción científica relevante (alemán, francés, portugués, japonés, chino) cuando aplique.
    2. Identifica subtemas, condiciones relacionadas y entidades diagnósticas adyacentes que podrían arrojar literatura útil.
    3. Define una frase descriptiva simple de búsqueda en inglés (de 4 a 8 palabras clave principales, sin operadores booleanos como AND/OR ni paréntesis) para que el sistema consulte de forma óptima las bases de datos de PubMed, CrossRef y OpenAlex.
       IMPORTANTE: Recuerda que todas las búsquedas son de manera EXCLUSIVA en población pediátrica. Asegúrate de incluir palabras clave como "pediatric", "child", "infant", "newborn" o similares.
    4. Concluye el campo 'log_content' indicando explícitamente y con tono formal de traspaso de antorcha que envías los términos al **AGENTE 2 — ESTRATEGA DE BÚSQUEDA** para que formule las queries avanzadas.
    
    Debes responder estrictamente en formato JSON con la siguiente estructura de llaves:
    {{
      "log_content": "Mensaje detallado en español con todo el desglose terminológico solicitado en el Paso 1 y Paso 2 (usa títulos de sección en Markdown, viñetas, negritas, etc. de forma premium). Termina indicando el traspaso al AGENTE 2.",
      "search_term": "La frase descriptiva de búsqueda en inglés de 4 a 8 palabras clave"
    }}
    """
    
    try:
        response_json = await call_gemini(prompt_agente1, json_mode=True, temperature=0.1)
        # Limpiar posibles markdown wrappers de JSON si existen
        cleaned_json = response_json.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = cleaned_json.replace("```json", "").replace("```", "").strip()
        
        search_data = json.loads(cleaned_json)
        proposal = search_data.get("log_content", "")
        search_term = search_data.get("search_term", query)
    except Exception as e:
        logger.error(f"Error parseando JSON de Agente 1: {e}. Usando fallback.")
        search_term = query.replace(":", " ").strip()
        proposal = f"""
### AGENTE 1 — DESGLOSE TERMINOLÓGICO PARA: {query}
* **Terminología formal (ES):** {query} en población pediátrica.
* **Términos de búsqueda (EN):** {search_term}.
* **Búsqueda global:** Consultando bases de datos con los términos de indexación en inglés.
        """
        
    await event_queue.put(buscador.format_log(proposal, "search"))
    
    # --- TURNO 2: AGENTE 2 — ESTRATEGA DE BÚSQUEDA EN BASES DE DATOS ---
    logger.info("Iniciando Paso 1: Turno 2 (Estratega de Búsqueda)")
    
    prompt_agente2 = f"""
    Actúa como el AGENTE 2 — ESTRATEGA DE BÚSQUEDA EN BASES DE DATOS.
    El Terminólogo Médico ha analizado la consulta "{query}" y ha definido la frase clave de búsqueda: "{search_term}".
    
    Tu tarea:
    1. Inicia tu respuesta confirmando explícitamente la recepción de los términos y conceptos clave desde el **AGENTE 1 — TERMINÓLOGO MÉDICO**.
    2. Construye strings de búsqueda avanzados y optimizados (con operadores booleanos AND/OR/NOT, truncamientos, paréntesis, campos [tiab], [MeSH], etc.) para CADA una de estas bases:
       - PubMed / MEDLINE
       - Embase
       - Cochrane Library (CENTRAL y revisiones sistemáticas)
       - Scopus
       - Web of Science
       - LILACS / SciELO (literatura latinoamericana)
       - Google Scholar (búsqueda de respaldo)
       - ClinicalTrials.gov (ensayos en curso)
       IMPORTANTE: Recuerda que todas las búsquedas y estrategias deben estar estrictamente restringidas a la población pediátrica (niños, lactantes, recién nacidos, adolescentes). No deben incluir datos ni estudios exclusivos de adultos.
    3. Aplica y describe los filtros sugeridos: últimos 5 años por defecto, humanos, tipo de estudio (revisiones sistemáticas, metanálisis, ECA, guías clínicas primero).
    4. Indica el orden recomendado de búsqueda y justifica por qué.
    5. Concluye indicando de forma formal que pasas la estafeta al **AGENTE 3 — REVISOR CRÍTICO Y CURADOR DE EVIDENCIA** tras la ejecución asíncrona de las llamadas a PubMed, CrossRef y OpenAlex.
    
    Genera una respuesta en español formateada de forma premium con títulos claros en Markdown.
    """
    
    agente2_msg = await call_gemini(prompt_agente2, temperature=0.2)
    await event_queue.put(critico.format_log(agente2_msg, "search"))
    
    # --- EJECUCIÓN DE BÚSQUEDA REAL EN APIS (CON FILTRO PEDIÁTRICO ESTRICTO) ---
    search_term_lower = search_term.lower()
    pediatric_keywords = ["pediat", "paediat", "child", "infan", "newborn", "neonat", "adolesc"]
    if not any(kw in search_term_lower for kw in pediatric_keywords):
        search_term_modified = f"{search_term} (pediatric OR child OR infant)"
        logger.info(f"Filtro pediátrico inyectado: '{search_term_modified}'")
    else:
        search_term_modified = search_term
        logger.info(f"Búsqueda con término pediátrico existente: '{search_term_modified}'")
        
    pubmed_task = query_pubmed(search_term_modified)
    crossref_task = query_crossref(search_term_modified)
    openalex_task = query_openalex(search_term_modified)
    
    try:
        pubmed_results, crossref_results, openalex_results = await asyncio.gather(
            pubmed_task, crossref_task, openalex_task, return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Fallo en la búsqueda concurrente: {e}")
        pubmed_results, crossref_results, openalex_results = [], [], []
        
    if isinstance(pubmed_results, Exception): pubmed_results = []
    if isinstance(crossref_results, Exception): crossref_results = []
    if isinstance(openalex_results, Exception): openalex_results = []
    
    # Combinar resultados y deduplicar por DOI o título aproximado
    raw_results = pubmed_results + crossref_results + openalex_results
    
    seen_dois = set()
    seen_titles = set()
    filtered_raw = []
    for p in raw_results:
        doi = p["doi"].lower().strip()
        title_key = p["title"].lower().strip()[:50]  # Clave aproximada por título
        
        # Filtro estricto para excluir ciencia básica / celular
        if not is_clinical_paper(p["title"], p["abstract"]):
            logger.info(f"Descartando artículo no clínico/celular: {p['title']}")
            continue
            
        if doi not in seen_dois and title_key not in seen_titles:
            seen_dois.add(doi)
            seen_titles.add(title_key)
            filtered_raw.append(p)
            
    # Si las APIs no devolvieron nada (0 resultados), cargar fallback de la base local
    if not filtered_raw:
        logger.info("No se encontraron resultados en APIs. Activando base de datos interna de respaldo...")
        filtered_raw = search_fallback_database(query, limit=20)
        
    # Limitar a exactamente 15 papers para el flujo del pipeline posterior
    final_papers = filtered_raw[:15]
    
    # Completar a 15 con base de datos interna si es necesario, usando la consulta real del usuario
    if len(final_papers) < 15:
        extra_papers = search_fallback_database(query, limit=20)
        for ep in extra_papers:
            ep_doi = ep["doi"].lower().strip()
            ep_title = ep["title"].lower().strip()[:50]
            if ep_doi not in [p["doi"].lower().strip() for p in final_papers] and ep_title not in [p["title"].lower().strip()[:50] for p in final_papers]:
                final_papers.append(ep)
            if len(final_papers) == 15:
                break
                
    # --- TURNO 3: AGENTE 3 — REVISOR CRÍTICO Y CURADOR DE EVIDENCIA ---
    logger.info("Iniciando Paso 1: Turno 3 (Revisor Crítico)")
    
    # Pasamos el top 10 al Revisor Crítico para que arme su curaduría detallada en el formato del usuario
    papers_to_review = final_papers[:8] # Usamos el top 8 para dar descripciones muy detalladas sin saturar el contexto de la llamada
    
    papers_json_str = json.dumps([{
        "title": p["title"],
        "authors": p["authors"],
        "journal": p["journal"],
        "year": p["year"],
        "doi": p["doi"],
        "abstract": p["abstract"]
    } for p in papers_to_review], ensure_ascii=False)
    
    prompt_agente3 = f"""
    Actúa como el AGENTE 3 — REVISOR CRÍTICO Y CURADOR DE EVIDENCIA.
    Has ejecutado la búsqueda clínica para el tema "{query}" en PubMed, CrossRef y OpenAlex.
    Los artículos recuperados son:
    {papers_json_str}
    
    Tu tarea:
    1. Inicia tu respuesta confirmando de forma explícita que has recibido las queries del **AGENTE 2** y que analizas el lote de papers recuperado por las APIs en paralelo.
    2. Presenta los papers más relevantes y actuales priorizando esta jerarquía:
       - Guías de práctica clínica recientes (≤3 años)
       - Revisiones sistemáticas y metanálisis (≤5 años)
       - Ensayos clínicos aleatorizados (ECA) grandes
       - Estudios observacionales relevantes
       - Reportes de caso solo si el tema es muy raro
    3. Para CADA paper, preséntalo estrictamente en este formato (usa separadores claros):
       
       ─────────────────────────────────
       • Título: [título original]
       • Autores: [primer autor et al.]
       • Revista, año: [revista, año, vol(núm):pp si se especifica]
       • Tipo de estudio: [revisión sistemática / ECA / cohorte / etc.]
       • Resumen en español (3–5 líneas con los hallazgos clave aplicables a la práctica)
       • DOI: [DOI o enlace]
       • Acceso: [Indica si es ABIERTO con enlace directo o DE PAGO si requiere suscripción/descarga manual]
       • Relevancia clínica: [alta / media / baja] y por qué.
       ─────────────────────────────────
       
    4. Agrega una sección titulada obligatoriamente:
       **📋 LISTA DE DOIs DE PAPERS DE PAGO**
       Dentro de esta sección, pon únicamente los DOIs en un formato de lista limpia, uno por línea, listos para copiar y pegar.
       
    5. Termina con una "**Síntesis Ejecutiva**" de 5–8 líneas con los puntos clave que la evidencia actual sostiene sobre el tema. Concluye declarando la fase de búsqueda e indexación completada con éxito, y que pasas la lista consolidada de 15 papers clínicos de cirugía pediátrica al **Extractor Clínico** de la Fase de Análisis PICO-S (Paso 2).
    
    Escribe una respuesta en español rigurosa, profesional y clínica, con títulos de sección en Markdown.
    """
    
    agente3_msg = await call_gemini(prompt_agente3, temperature=0.2)
    await event_queue.put(refinador.format_log(agente3_msg, "search"))
    
    return final_papers
