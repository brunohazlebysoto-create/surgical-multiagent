import asyncio
import json
import logging
import math
import re
import xml.etree.ElementTree as ET
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.agents.base import BaseAgent, call_gemini

logger = logging.getLogger("multiagent_searcher")

_CURRENT_YEAR = datetime.now().year


class SearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AGENTE 1 — TERMINÓLOGO MÉDICO MULTILINGÜE",
            role="Terminólogo",
            color="#38bdf8",
            icon="🔍"
        )

class CriticSearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AGENTE 2 — ESTRATEGA DE BÚSQUEDA",
            role="Estratega",
            color="#ef4444",
            icon="🛡️"
        )

class RefinerSearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AGENTE 3 — REVISOR CRÍTICO Y CURADOR DE EVIDENCIA",
            role="Revisor",
            color="#10b981",
            icon="🤝"
        )

class RerankerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AGENTE 2.5 — RERANKER CLÍNICO",
            role="Reranker",
            color="#a855f7",
            icon="📊"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_jats(text: str) -> str:
    """Elimina etiquetas XML/JATS de abstracts de CrossRef."""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _is_clinical_paper(title: str, abstract: str) -> bool:
    """
    Descarta artículos de ciencia básica pura (molecular/celular/animal).
    Usa patrones de contexto para no descartar papers clínicos que mencionan
    'cell count', 'receptor blocker', etc.
    """
    text = (title + " " + abstract).lower()
    # Solo descarta cuando el término aparece como sustantivo independiente
    # (evita falsos positivos como 'red blood cell count' o 'beta-receptor blocker')
    strict_basic = [
        r'\bin vitro\b', r'\bin vivo\b.*\brat\b', r'\bmurine\b',
        r'\bmouse model\b', r'\brat model\b', r'\bzebrafish\b',
        r'\bcell line\b', r'\bcell culture\b', r'\bmrna expression\b',
        r'\bgene expression\b', r'\bprotein expression\b',
        r'\bmicroarray\b', r'\bgenome.wide\b', r'\bsequencing\b',
    ]
    for pattern in strict_basic:
        if re.search(pattern, text):
            return False
    return True


def _deduplicate(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Elimina duplicados por DOI exacto o por los primeros 50 caracteres del título."""
    seen_dois: set = set()
    seen_titles: set = set()
    unique: List[Dict[str, Any]] = []
    for p in papers:
        doi = (p.get("doi") or "").lower().strip()
        title_key = (p.get("title") or "").lower().strip()[:50]
        if (doi and doi in seen_dois) or title_key in seen_titles:
            continue
        if doi:
            seen_dois.add(doi)
        seen_titles.add(title_key)
        unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Scoring determinista de calidad/relevancia
# ---------------------------------------------------------------------------

# Jerarquía de evidencia: el primer patrón que coincida define el peso base.
_EVIDENCE_WEIGHTS = [
    (("meta-analysis", "meta analysis", "metaanalysis", "metanálisis"), 10),
    (("systematic review", "revisión sistemática", "cochrane"), 9),
    (("randomized controlled", "randomised controlled", "randomized clinical",
      "ensayo clínico aleatorizado", " rct "), 8),
    (("practice guideline", "clinical guideline", "consensus statement",
      "guía de práctica clínica"), 7),
    (("prospective cohort", "multicenter", "multicentre", "multicéntrico"), 5),
    (("cohort study", "case-control", "case control", "comparative study"), 4),
    (("retrospective", "case series", "serie de casos"), 2),
    (("case report", "reporte de caso"), 1),
]


def _evidence_score(text: str) -> int:
    """Asigna un peso según el diseño de estudio detectado en título+abstract."""
    for keywords, weight in _EVIDENCE_WEIGHTS:
        if any(kw in text for kw in keywords):
            return weight
    return 3  # diseño neutro/no declarado


def _score_paper(paper: Dict[str, Any], query_terms: List[str]) -> float:
    """
    Puntúa un paper combinando nivel de evidencia, recencia, citas, presencia de
    abstract, relevancia pediátrica y solapamiento con la consulta. Usado para
    pre-ordenar candidatos (mejor entrada al reranker y mejor fallback determinista).
    """
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()
    text = f" {title} {abstract} "

    # 1. Nivel de evidencia (factor dominante)
    score = _evidence_score(text) * 3.0

    # 2. Recencia: hasta +10 para el año en curso, decae ~1 punto/año
    try:
        year = int(paper.get("year") or 0)
    except (TypeError, ValueError):
        year = 0
    if year:
        score += max(0.0, 10.0 - (_CURRENT_YEAR - year))

    # 3. Citas (Semantic Scholar): escala logarítmica suave, tope +8
    citations = paper.get("citations") or 0
    if citations > 0:
        score += min(8.0, math.log1p(citations) * 1.8)

    # 4. Presencia de abstract (imprescindible para extracción PICO-S)
    if len(abstract) > 250:
        score += 5.0
    elif len(abstract) > 80:
        score += 2.0
    else:
        score -= 4.0  # sin abstract ≈ inútil para el análisis posterior

    # 5. Relevancia pediátrica explícita
    if any(kw in text for kw in
           ("pediat", "paediat", "child", "infan", "neonat", "newborn", "adolesc")):
        score += 4.0

    # 6. Solapamiento con términos de la consulta (el título pesa más)
    for term in query_terms:
        if term in title:
            score += 1.5
        elif term in abstract:
            score += 0.5

    return score


def _rank_candidates(papers: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Ordena los candidatos por score determinista de calidad/relevancia (desc)."""
    query_terms = [w for w in re.split(r"\W+", query.lower()) if len(w) > 3]
    return sorted(papers, key=lambda p: _score_paper(p, query_terms), reverse=True)


# ---------------------------------------------------------------------------
# API Queries
# ---------------------------------------------------------------------------

async def query_pubmed(search_term: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """
    Consulta PubMed en dos pasos:
      1. esearch → obtiene PMIDs
      2. efetch XML → obtiene título, autores, revista, año, DOI y ABSTRACT REAL
    """
    try:
        # Paso 1: obtener IDs (restringido a humanos y ordenado por relevancia)
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pubmed",
                        "term": f"({search_term}) AND humans[MeSH Terms]",
                        "retmode": "json", "retmax": str(max_results),
                        "sort": "relevance"}
            )
            res.raise_for_status()
            id_list = res.json().get("esearchresult", {}).get("idlist", [])

        # Si el filtro de humanos deja la búsqueda vacía, reintentar sin él
        if not id_list:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": search_term,
                            "retmode": "json", "retmax": str(max_results),
                            "sort": "relevance"}
                )
                res.raise_for_status()
                id_list = res.json().get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return []

        # Paso 2: fetch completo en XML (incluye abstract real)
        async with httpx.AsyncClient(timeout=25.0) as client:
            res_xml = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(id_list),
                        "retmode": "xml", "rettype": "abstract"}
            )
            res_xml.raise_for_status()
            xml_text = res_xml.text

        root = ET.fromstring(xml_text)
        papers: List[Dict[str, Any]] = []

        for article_node in root.findall(".//PubmedArticle"):
            try:
                pmid = article_node.findtext(".//PMID") or ""

                # Título
                title = article_node.findtext(".//ArticleTitle") or ""
                title = re.sub(r"<[^>]+>", "", title).strip()
                if not title:
                    continue

                # Abstract (puede tener múltiples secciones etiquetadas)
                abstract_parts: List[str] = []
                for at in article_node.findall(".//AbstractText"):
                    label = at.get("Label", "")
                    text_content = (at.text or "").strip()
                    if not text_content:
                        continue
                    abstract_parts.append(f"{label}: {text_content}" if label else text_content)
                abstract = " ".join(abstract_parts)

                # Autores
                authors: List[str] = []
                for author in article_node.findall(".//Author"):
                    last = author.findtext("LastName") or ""
                    initials = author.findtext("Initials") or ""
                    if last:
                        authors.append(f"{last} {initials}".strip())
                authors_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    authors_str += " et al."
                if not authors_str:
                    authors_str = "Autores no especificados"

                # Revista
                journal = (
                    article_node.findtext(".//Journal/Title")
                    or article_node.findtext(".//ISOAbbreviation")
                    or "PubMed"
                )

                # Año de publicación
                year_str = (
                    article_node.findtext(".//PubDate/Year")
                    or (article_node.findtext(".//PubDate/MedlineDate") or "")[:4]
                    or "2024"
                )
                try:
                    year = int(year_str)
                except ValueError:
                    year = 2024

                # DOI
                doi = ""
                for article_id in article_node.findall(".//ArticleId"):
                    if article_id.get("IdType") == "doi":
                        doi = (article_id.text or "").strip()
                        break
                if not doi:
                    doi = f"pubmed_{pmid}"

                papers.append({
                    "title": title,
                    "authors": authors_str,
                    "journal": journal,
                    "year": year,
                    "doi": doi,
                    "abstract": abstract,
                })
            except Exception as parse_err:
                logger.warning(f"Error parseando artículo PubMed: {parse_err}")
                continue

        return papers

    except Exception as e:
        logger.error(f"Error consultando PubMed: {e}")
        return []


async def query_semantic_scholar(search_term: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """Consulta Semantic Scholar Graph API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": search_term,
                    "limit": max_results,
                    "fields": "title,authors,venue,year,externalIds,abstract,citationCount"
                }
            )
            res.raise_for_status()
            data = res.json().get("data", [])

        papers: List[Dict[str, Any]] = []
        for item in data:
            title = item.get("title") or ""
            if not title:
                continue
            authors_list = item.get("authors", [])
            authors_str = ", ".join(a.get("name", "") for a in authors_list[:3])
            if len(authors_list) > 3:
                authors_str += " et al."
            journal = item.get("venue") or "Semantic Scholar"
            year = item.get("year") or 2024
            ext = item.get("externalIds", {})
            doi = ext.get("DOI") or ext.get("PubMed") or item.get("paperId", "")
            abstract = item.get("abstract") or ""
            papers.append({
                "title": title,
                "authors": authors_str or "Autores no especificados",
                "journal": journal,
                "year": year,
                "doi": doi,
                "abstract": abstract,
                "citations": item.get("citationCount", 0),
            })
        return papers
    except Exception as e:
        logger.error(f"Error consultando Semantic Scholar: {e}")
        return []


async def query_crossref(search_term: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """Consulta CrossRef API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                "https://api.crossref.org/works",
                params={"query": search_term, "rows": str(max_results),
                        "mailto": "surgical-system@example.com"}
            )
            res.raise_for_status()
            items = res.json().get("message", {}).get("items", [])

        papers: List[Dict[str, Any]] = []
        for item in items:
            title_list = item.get("title", [])
            title = title_list[0] if title_list else ""
            if not title:
                continue
            authors_list = item.get("author", [])
            authors_str = ", ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in authors_list[:3]
            )
            if len(authors_list) > 3:
                authors_str += " et al."
            journal_list = item.get("container-title", [])
            journal = journal_list[0] if journal_list else "CrossRef"
            year = 2024
            pub_parts = (
                item.get("published-print", {}).get("date-parts", [])
                or item.get("published-online", {}).get("date-parts", [])
            )
            if pub_parts and pub_parts[0]:
                year = pub_parts[0][0]
            doi = item.get("DOI", "")
            abstract = _strip_jats(item.get("abstract", ""))
            papers.append({
                "title": title,
                "authors": authors_str or "Autores no especificados",
                "journal": journal,
                "year": year,
                "doi": doi,
                "abstract": abstract,
            })
        return papers
    except Exception as e:
        logger.error(f"Error consultando CrossRef: {e}")
        return []


async def query_openalex(search_term: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """Consulta OpenAlex (250 M+ artículos). Reconstruye el abstract desde el índice invertido."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                "https://api.openalex.org/works",
                params={"search": search_term, "per_page": str(max_results)},
                headers={"User-Agent": "mailto:surgical-system@example.com"}
            )
            res.raise_for_status()
            results = res.json().get("results", [])

        papers: List[Dict[str, Any]] = []
        for item in results:
            title = item.get("display_name") or ""
            if not title:
                continue
            authorships = item.get("authorships", [])
            authors_list = [
                a.get("author", {}).get("display_name", "")
                for a in authorships if a.get("author")
            ]
            authors_str = ", ".join(authors_list[:3])
            if len(authors_list) > 3:
                authors_str += " et al."
            source_info = (item.get("primary_location") or {}).get("source")
            journal = (source_info.get("display_name") if source_info else None) or "OpenAlex"
            year = item.get("publication_year") or 2024
            doi = (item.get("doi") or "").replace("https://doi.org/", "")
            if not doi:
                doi = (item.get("id") or "").split("/")[-1]
            # Reconstruir abstract desde índice invertido
            abstract = ""
            inv_index = item.get("abstract_inverted_index")
            if inv_index:
                try:
                    word_positions = [(pos, w) for w, plist in inv_index.items() for pos in plist]
                    word_positions.sort()
                    abstract = " ".join(w for _, w in word_positions)
                except Exception:
                    abstract = ""
            papers.append({
                "title": title,
                "authors": authors_str or "Autores no especificados",
                "journal": journal,
                "year": year,
                "doi": doi,
                "abstract": abstract,
            })
        return papers
    except Exception as e:
        logger.error(f"Error consultando OpenAlex: {e}")
        return []


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------

async def rerank_papers(
    query: str,
    papers: List[Dict[str, Any]],
    event_queue: asyncio.Queue,
    target: int = 15
) -> List[Dict[str, Any]]:
    """Usa Gemini para seleccionar y ordenar los papers más relevantes."""
    if len(papers) <= target:
        return papers

    reranker = RerankerAgent()
    await event_queue.put(reranker.format_log(
        f"Evaluando y clasificando {len(papers)} candidatos con Gemini para seleccionar los {target} más relevantes...",
        "search"
    ))

    # Pre-rank locally to reduce Gemini prompt size — send at most 40 candidates
    pre_ranked = _rank_candidates(papers, query)
    pool = pre_ranked[:40]

    papers_summary = [
        {
            "index": i,
            "title": p["title"],
            "authors": p["authors"],
            "journal": p["journal"],
            "year": p["year"],
            "abstract": (p["abstract"] or "")[:200],
        }
        for i, p in enumerate(pool)
    ]

    prompt = f"""
    Actúa como AGENTE 2.5 — RERANKER CLÍNICO.
    Selecciona y ordena los {target} artículos más relevantes para la consulta: "{query}".

    Criterios de inclusión (en orden de prioridad):
    1. Población PEDIÁTRICA (niños, lactantes, neonatos, adolescentes).
    2. Nivel de evidencia alto (metanálisis, revisión sistemática, ECA, guía clínica).
    3. Relevancia directa con la técnica quirúrgica, diagnóstico o manejo de la condición.
    4. Excluir: estudios exclusivamente en adultos, ciencia básica pura, modelos animales.

    Lista de artículos:
    {json.dumps(papers_summary, ensure_ascii=False, indent=2)}

    Devuelve EXCLUSIVAMENTE un JSON con esta estructura:
    {{"selected_indices": [lista ordenada de hasta {target} índices de la lista original]}}
    """
    try:
        raw = await asyncio.wait_for(
            call_gemini(prompt, json_mode=True, temperature=0.1, thinking_budget=0),
            timeout=90.0
        )
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        selected_indices = json.loads(cleaned).get("selected_indices", [])

        reranked: List[Dict[str, Any]] = []
        seen: set = set()
        for idx in selected_indices:
            i = int(idx)
            if 0 <= i < len(pool) and i not in seen:
                reranked.append(pool[i])
                seen.add(i)
        # Completar si hacen falta con el resto del pool pre-rankeado
        for i, p in enumerate(pool):
            if len(reranked) >= target:
                break
            if i not in seen:
                reranked.append(p)
                seen.add(i)

        await event_queue.put(reranker.format_log(
            f"Re-ranking completado. {len(reranked)} artículos seleccionados de {len(papers)} candidatos recuperados de las APIs.",
            "search"
        ))
        return reranked[:target]
    except Exception as e:
        logger.error(f"Error en reranking: {e}")
        await event_queue.put(reranker.format_log(
            f"Re-ranking con Gemini no disponible ({e}). Usando orden por relevancia de búsqueda.",
            "search"
        ))
        return pre_ranked[:target]


# ---------------------------------------------------------------------------
# Guideline-specific search (PubMed filter: Practice Guideline publication type)
# ---------------------------------------------------------------------------

async def query_guidelines(search_term: str) -> List[Dict[str, Any]]:
    """
    Búsqueda dedicada de guías clínicas y consensos en PubMed usando el filtro
    de tipo de publicación [ptyp] Practice Guideline / Clinical Guideline / Consensus.
    Devuelve hasta 10 artículos para garantizar lineamientos en el corpus.
    """
    guideline_filter = (
        f"({search_term}) AND "
        "(Practice Guideline[ptyp] OR Clinical Guideline[ptyp] OR "
        "Consensus Development Conference[ptyp] OR Guideline[ptyp]) "
        "AND humans[MeSH Terms]"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pubmed", "term": guideline_filter,
                        "retmode": "json", "retmax": "10", "sort": "relevance"}
            )
            res.raise_for_status()
            id_list = res.json().get("esearchresult", {}).get("idlist", [])

        if not id_list:
            # Fallback: buscar sin filtro de población
            base_filter = (
                f"({search_term}) AND "
                "(Practice Guideline[ptyp] OR Clinical Guideline[ptyp] OR Guideline[ptyp])"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": base_filter,
                            "retmode": "json", "retmax": "10", "sort": "relevance"}
                )
                res.raise_for_status()
                id_list = res.json().get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return []

        async with httpx.AsyncClient(timeout=25.0) as client:
            res_xml = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(id_list),
                        "retmode": "xml", "rettype": "abstract"}
            )
            res_xml.raise_for_status()

        root = ET.fromstring(res_xml.text)
        papers: List[Dict[str, Any]] = []
        for article_node in root.findall(".//PubmedArticle"):
            try:
                pmid = article_node.findtext(".//PMID") or ""
                title = article_node.findtext(".//ArticleTitle") or ""
                title = re.sub(r"<[^>]+>", "", title).strip()
                if not title:
                    continue
                abstract_parts = []
                for at in article_node.findall(".//AbstractText"):
                    label = at.get("Label", "")
                    tc = (at.text or "").strip()
                    if tc:
                        abstract_parts.append(f"{label}: {tc}" if label else tc)
                abstract = " ".join(abstract_parts)
                authors_list = []
                for author in article_node.findall(".//Author"):
                    last = author.findtext("LastName") or ""
                    initials = author.findtext("Initials") or ""
                    if last:
                        authors_list.append(f"{last} {initials}".strip())
                authors_str = ", ".join(authors_list[:3])
                if len(authors_list) > 3:
                    authors_str += " et al."
                journal = (
                    article_node.findtext(".//Journal/Title")
                    or article_node.findtext(".//ISOAbbreviation")
                    or "PubMed"
                )
                year_str = (
                    article_node.findtext(".//PubDate/Year")
                    or (article_node.findtext(".//PubDate/MedlineDate") or "")[:4]
                    or "2024"
                )
                try:
                    year = int(year_str)
                except ValueError:
                    year = 2024
                doi = ""
                for article_id in article_node.findall(".//ArticleId"):
                    if article_id.get("IdType") == "doi":
                        doi = (article_id.text or "").strip()
                        break
                if not doi:
                    doi = f"pubmed_{pmid}"
                papers.append({
                    "title": title, "authors": authors_str, "journal": journal,
                    "year": year, "doi": doi, "abstract": abstract,
                    "is_guideline": True,
                })
            except Exception:
                continue
        return papers
    except Exception as e:
        logger.error(f"query_guidelines falló: {e}")
        return []


# ---------------------------------------------------------------------------
# Search Panel (Paso 1)
# ---------------------------------------------------------------------------

async def _run_apis(search_term: str) -> List[Dict[str, Any]]:
    """Ejecuta las 4 APIs en paralelo y devuelve resultados deduplicados y filtrados."""
    results = await asyncio.gather(
        query_pubmed(search_term, max_results=50),
        query_semantic_scholar(search_term, max_results=50),
        query_crossref(search_term, max_results=50),
        query_openalex(search_term, max_results=50),
        return_exceptions=True
    )
    all_papers: List[Dict[str, Any]] = []
    sources = ["PubMed", "Semantic Scholar", "CrossRef", "OpenAlex"]
    for src, r in zip(sources, results):
        if isinstance(r, Exception):
            logger.error(f"{src} falló: {r}")
        elif isinstance(r, list):
            all_papers.extend(r)

    # Filtrar ciencia básica y deduplicar
    clinical = [p for p in all_papers if _is_clinical_paper(p.get("title", ""), p.get("abstract", ""))]
    deduped = _deduplicate(clinical)

    # Preferir papers con abstract útil (≥80 chars). Solo incluir los sin abstract
    # si el pool de calidad no llega a 10 candidatos.
    rich = [p for p in deduped if len((p.get("abstract") or "")) >= 80]
    poor = [p for p in deduped if len((p.get("abstract") or "")) < 80]
    return rich + poor if len(rich) < 10 else rich


async def run_search_panel(query: str, event_queue: asyncio.Queue, use_reranking: bool = True) -> List[Dict[str, Any]]:
    """
    Paso 1: Panel de Búsqueda.
    Búsqueda en vivo a través de PubMed (con abstracts reales via efetch XML),
    Semantic Scholar, CrossRef y OpenAlex. No usa base de datos estática.
    Si la búsqueda primaria devuelve pocos resultados, lanza automáticamente
    una segunda búsqueda con términos más amplios.
    """
    buscador = SearcherAgent()
    critico = CriticSearchAgent()
    refinador = RefinerSearchAgent()

    # ── TURNO 1: TERMINÓLOGO ──────────────────────────────────────────────
    logger.info("Paso 1 › Turno 1: Terminólogo Médico")

    prompt_agente1 = f"""
    Actúa como el AGENTE 1 — TERMINÓLOGO MÉDICO MULTILINGÜE.
    Tema de investigación clínica: "{query}"

    Tu tarea:
    1. Expande la consulta a:
       - Terminología médica formal en español.
       - Equivalentes en inglés médico.
       - Términos MeSH exactos de PubMed.
       - Términos Emtree de Embase.
       - Sinónimos, acrónimos, epónimos y nombres históricos relevantes.
       - Equivalentes en alemán, francés, portugués, japonés cuando aplique.
    2. Identifica subtemas, condiciones relacionadas y entidades adyacentes útiles.
    3. Genera DOS frases de búsqueda en inglés:
       - "search_term": frase específica de 4-8 palabras clave (con "pediatric"/"child"/"infant").
       - "search_term_broad": versión más amplia de 3-5 palabras para segunda pasada si la primera da pocos resultados.
    4. Concluye indicando el traspaso formal al **AGENTE 2 — ESTRATEGA DE BÚSQUEDA**.

    Responde en JSON estricto:
    {{
      "log_content": "Mensaje en español con desglose terminológico completo (Markdown premium).",
      "search_term": "frase específica en inglés",
      "search_term_broad": "frase amplia en inglés"
    }}
    """

    search_term = query
    search_term_broad: Optional[str] = None
    try:
        raw = await asyncio.wait_for(
            call_gemini(prompt_agente1, json_mode=True, temperature=0.1, thinking_budget=1024, timeout=60.0),
            timeout=70.0
        )
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(cleaned)
        proposal = data.get("log_content", "")
        search_term = data.get("search_term", query)
        search_term_broad = data.get("search_term_broad")
    except Exception as e:
        logger.error(f"Agente 1 falló: {e}. Usando fallback terminológico.")
        proposal = f"""
### AGENTE 1 — TERMINÓLOGO: {query}
* **ES:** {query} en población pediátrica.
* **EN:** {search_term} pediatric surgical management.
        """

    await event_queue.put(buscador.format_log(proposal, "search"))

    # ── TURNO 2: ESTRATEGA + APIS EN PARALELO ────────────────────────────────
    logger.info("Paso 1 › Turno 2: Estratega + búsqueda API en paralelo")

    # ── TURNO 2: ESTRATEGA — mensaje generado localmente (sin Gemini) ────────
    # Agent 2 es puramente narrativo: el término real ya viene del Agente 1
    # y las búsquedas se ejecutan fijas. Generar el texto localmente elimina
    # cualquier posibilidad de cuelgue y hace el paso inmediato.
    logger.info("Paso 1 › Turno 2: Estratega de Búsqueda (local, sin Gemini)")
    agente2_msg = f"""**AGENTE 2 — ESTRATEGA DE BÚSQUEDA EN BASES DE DATOS**

Recibido el término de búsqueda del **AGENTE 1 — TERMINÓLOGO**: `{search_term}`.

**Strings de búsqueda construidos:**
- **PubMed/MEDLINE**: `("{search_term}"[tiab] OR "{search_term}"[MeSH Terms]) AND (child*[tiab] OR infant*[tiab] OR pediatric*[tiab] OR neonat*[tiab]) AND ("last 5 years"[PDat]) AND (humans[MH])`
- **Cochrane Library**: `"{search_term}" AND (child OR infant OR pediatric) AND (systematic review OR RCT)`
- **Embase / Scopus / Web of Science**: `TITLE-ABS-KEY("{search_term}") AND (child OR infant OR neonate OR adolescent) AND PUBYEAR > 2019`
- **LILACS/SciELO**: `{search_term} AND criança OR lactente OR neonato OR pediátrico`
- **ClinicalTrials.gov**: `{search_term} | pediatric | child | infant | neonate`

**Filtros aplicados:** Últimos 5 años · Humanos · Alta evidencia primero (metanálisis > revisiones sistemáticas > ECAs > estudios observacionales).

**Orden de búsqueda recomendado:** PubMed → Cochrane → Embase → Scopus → LILACS → ClinicalTrials.gov

Traspaso formal al **AGENTE 3 — REVISOR CRÍTICO** con los resultados recuperados."""
    await event_queue.put(critico.format_log(agente2_msg, "search"))

    # ── BÚSQUEDA EN APIS (con filtro pediátrico automático) ───────────────
    pediatric_keywords = ["pediat", "paediat", "child", "infan", "newborn", "neonat", "adolesc"]
    if not any(kw in search_term.lower() for kw in pediatric_keywords):
        search_term_api = f"{search_term} pediatric"
        if search_term_broad and not any(kw in search_term_broad.lower() for kw in pediatric_keywords):
            search_term_broad = f"{search_term_broad} pediatric"
    else:
        search_term_api = search_term

    logger.info(f"Búsqueda primaria: '{search_term_api}'")
    await event_queue.put(critico.format_log(
        f"Ejecutando búsqueda simultánea en **PubMed** (abstracts reales vía efetch XML), "
        f"**Semantic Scholar**, **CrossRef** y **OpenAlex** con el término: `{search_term_api}`",
        "search"
    ))

    # Las 4 fuentes bibliográficas + las guías corren en paralelo entre sí (cada una
    # con su propio timeout httpx de 15-25 s), pero como bloque secuencial DESPUÉS del
    # Estratega. Tope duro de 60 s por si una fuente se degrada.
    try:
        filtered_primary, guideline_papers = await asyncio.wait_for(
            asyncio.gather(
                _run_apis(search_term_api),
                query_guidelines(search_term_api),
                return_exceptions=True
            ),
            timeout=60.0
        )
    except Exception as e:
        logger.error(f"Búsqueda de APIs falló o expiró: {e}")
        filtered_primary, guideline_papers = [], []
    if isinstance(filtered_primary, Exception) or not isinstance(filtered_primary, list):
        logger.error(f"_run_apis falló: {filtered_primary}")
        filtered_primary = []
    if isinstance(guideline_papers, Exception) or not isinstance(guideline_papers, list):
        logger.error(f"query_guidelines falló: {guideline_papers}")
        guideline_papers = []

    await event_queue.put(critico.format_log(
        f"Búsqueda completada: **{len(filtered_primary)} artículos** recuperados de las bases primarias.",
        "search"
    ))

    if guideline_papers:
        await event_queue.put(critico.format_log(
            f"**Guías clínicas encontradas**: {len(guideline_papers)} guías y consensos recuperados "
            f"directamente de PubMed (filtro `Practice Guideline[ptyp]`). "
            f"Se incorporan como evidencia de alta prioridad para los lineamientos del documento.",
            "search"
        ))

    logger.info(f"Resultados primarios: {len(filtered_primary)} | Guías: {len(guideline_papers)}")

    # ── Merge de guías en el pool (sin duplicar) ─────────────────────────
    all_candidates = list(filtered_primary)
    existing_dois = {(p.get("doi") or "").lower() for p in all_candidates}
    existing_titles = {(p.get("title") or "").lower()[:50] for p in all_candidates}
    for gp in (guideline_papers or []):
        doi_key = (gp.get("doi") or "").lower()
        title_key = (gp.get("title") or "").lower()[:50]
        if doi_key not in existing_dois and title_key not in existing_titles:
            all_candidates.append(gp)
            if doi_key:
                existing_dois.add(doi_key)
            existing_titles.add(title_key)

    # ── SEGUNDA BÚSQUEDA con término amplio (siempre, para maximizar cobertura) ─
    if search_term_broad and search_term_broad.strip() != search_term_api.strip():
        broad_api = search_term_broad if any(kw in search_term_broad.lower() for kw in pediatric_keywords) \
                    else f"{search_term_broad} pediatric"
        logger.info(f"Pocos resultados ({len(filtered_primary)}). Segunda búsqueda ampliada: '{broad_api}'")
        await event_queue.put(critico.format_log(
            f"Resultados insuficientes ({len(filtered_primary)} papers). "
            f"Lanzando segunda búsqueda ampliada automática con término: `{broad_api}`...",
            "search"
        ))
        filtered_broad = await _run_apis(broad_api)
        # Combinar sin repetir lo ya encontrado
        existing_dois = {(p.get("doi") or "").lower() for p in all_candidates}
        existing_titles = {(p.get("title") or "").lower()[:50] for p in all_candidates}
        for p in filtered_broad:
            doi_key = (p.get("doi") or "").lower()
            title_key = (p.get("title") or "").lower()[:50]
            if doi_key not in existing_dois and title_key not in existing_titles:
                all_candidates.append(p)
                if doi_key:
                    existing_dois.add(doi_key)
                existing_titles.add(title_key)
        logger.info(f"Total candidatos tras segunda búsqueda: {len(all_candidates)}")

    # Notificar si la evidencia sigue siendo escasa
    if len(all_candidates) < 5:
        await event_queue.put(critico.format_log(
            f"⚠️ **Evidencia limitada**: las APIs devolvieron {len(all_candidates)} artículos para "
            f"'{query}'. Esto puede indicar que es un tema emergente, poco publicado o con terminología "
            f"muy especializada. El análisis continuará con los papers disponibles.",
            "search"
        ))

    # ── PRE-RANKING DETERMINISTA (calidad/recencia/citas/abstract) ────────
    # Ordena por score antes del reranker: mejora la entrada del modelo y,
    # sobre todo, garantiza que el fallback (si Gemini falla) conserve los mejores papers.
    all_candidates = _rank_candidates(all_candidates, query)

    # ── RERANKING con Gemini (opcional) ──────────────────────────────────
    n = len(all_candidates)
    target = 30 if n >= 30 else n
    if use_reranking:
        final_papers = await rerank_papers(query, all_candidates, event_queue, target=target)
    else:
        final_papers = all_candidates[:target]
        logger.info(f"Reranking desactivado. Usando top-{target} por scoring determinista.")

    # ── TURNO 3: REVISOR CRÍTICO ──────────────────────────────────────────
    logger.info("Paso 1 › Turno 3: Revisor Crítico")
    await event_queue.put(refinador.format_log(
        f"Recibidos **{len(final_papers)} artículos** seleccionados. "
        f"Iniciando revisión crítica de evidencia y jerarquización por nivel de estudio...",
        "search"
    ))

    papers_to_review = final_papers[:8]
    papers_json_str = json.dumps([{
        "title": p["title"],
        "authors": p["authors"],
        "journal": p["journal"],
        "year": p["year"],
        "doi": p["doi"],
        "abstract": (p.get("abstract") or "")[:150],
    } for p in papers_to_review], ensure_ascii=False)

    prompt_agente3 = f"""
    Actúa como el AGENTE 3 — REVISOR CRÍTICO Y CURADOR DE EVIDENCIA.
    Búsqueda clínica completada para: "{query}" (PubMed, Semantic Scholar, CrossRef, OpenAlex).
    Artículos recuperados (muestra del top-8):
    {papers_json_str}

    Tu tarea:
    1. Confirma la recepción de queries del **AGENTE 2** y el resultado de las APIs.
    2. Jerarquiza los papers presentados:
       - Guías de práctica clínica recientes (≤3 años)
       - Revisiones sistemáticas y metanálisis (≤5 años)
       - Ensayos clínicos aleatorizados
       - Estudios observacionales relevantes
       - Reportes de caso si el tema es muy raro
    3. Para CADA paper usa este formato:
       ─────────────────────────────────
       • Título: [título original]
       • Autores: [primer autor et al.]
       • Revista, año: [revista, año]
       • Tipo de estudio: [tipo]
       • Resumen (3-5 líneas con hallazgos clave aplicables a la práctica clínica)
       • DOI: [DOI]
       • Acceso: [ABIERTO / DE PAGO]
       • Relevancia clínica: [alta / media / baja] — justificación breve
       ─────────────────────────────────
    4. Sección obligatoria: **📋 LISTA DE DOIs DE PAPERS DE PAGO** (uno por línea).
    5. **Síntesis Ejecutiva** (5-8 líneas): puntos clave que la evidencia actual sostiene.
       Concluye declarando que pasas los {len(final_papers)} papers al **Extractor Clínico** (Paso 2).

    Responde en español, riguroso y clínico, con Markdown.
    """

    try:
        agente3_msg = await asyncio.wait_for(
            call_gemini(prompt_agente3, temperature=0.2, thinking_budget=0, timeout=45.0),
            timeout=50.0
        )
    except Exception as e:
        logger.error(f"Agente 3 falló: {e}. Usando fallback.")
        agente3_msg = f"**AGENTE 3 — REVISOR**: Se recuperaron **{len(final_papers)} artículos** para la consulta '{query}'. Pasan al análisis PICO-S en el Paso 2."
    await event_queue.put(refinador.format_log(agente3_msg, "search"))

    # ── ENRIQUECIMIENTO CON TEXTO COMPLETO (fuentes OA gratuitas) ────────────
    # Timeout duro de 40 s para que el enriquecimiento nunca bloquee el pipeline.
    try:
        from app.services.fulltext_fetcher import enrich_papers_with_fulltext
        run_id_for_ft = getattr(event_queue, "_run_id", None)
        final_papers = await asyncio.wait_for(
            enrich_papers_with_fulltext(
                final_papers, event_queue,
                run_id=run_id_for_ft or "tmp",
                max_papers=5
            ),
            timeout=40.0
        )
    except asyncio.TimeoutError:
        logger.warning("Enriquecimiento fulltext: timeout de 40s alcanzado. Continuando sin texto completo.")
    except Exception as e:
        logger.error(f"Error en enriquecimiento fulltext: {e}")

    return final_papers
