"""
fulltext_fetcher.py
===================
Busca y descarga PDFs gratuitos legales usando múltiples fuentes de acceso abierto:

1. Unpaywall  — estándar de oro para OA legal por DOI (gratis, sin clave)
2. Europe PMC — artículos con PMC ID tienen texto completo libre
3. OpenAlex   — campo open_access.oa_url
4. Semantic Scholar — openAccessPdf
5. CORE API   — agregador global de OA (sin clave, limitado)
6. PubMed Central — efetch para PMC IDs

Todas las fuentes son 100 % legales (copias autorizadas por los autores o repositorios OA).
"""

import asyncio
import logging
import os
import re
import httpx
from typing import Optional, Tuple

logger = logging.getLogger("fulltext_fetcher")

# Email requerido por Unpaywall y OpenAlex (identificación educada, sin autenticación)
_OA_EMAIL = "surgical-multiagent@openaccess.org"

# Tiempos cortos para no bloquear el pipeline (el enriquecimiento es opcional)
_TIMEOUT = 8.0
_PDF_TIMEOUT = 15.0

# Timeout objeto con connect corto para evitar cuelgues TCP en redes restringidas
_API_TIMEOUT = httpx.Timeout(connect=4.0, read=_TIMEOUT, write=4.0, pool=4.0)
_DL_TIMEOUT = httpx.Timeout(connect=4.0, read=_PDF_TIMEOUT, write=4.0, pool=4.0)


# ---------------------------------------------------------------------------
# Unpaywall  (https://unpaywall.org/products/api)
# ---------------------------------------------------------------------------

async def _unpaywall_url(doi: str) -> Optional[str]:
    """Consulta Unpaywall por DOI y devuelve la URL del mejor PDF libre encontrado."""
    if not doi or doi.startswith("pubmed_") or doi.startswith("user_upload_"):
        return None
    url = f"https://api.unpaywall.org/v2/{doi}?email={_OA_EMAIL}"
    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf") or best.get("url")
            if pdf_url:
                logger.info(f"Unpaywall encontró PDF para DOI {doi}: {pdf_url}")
            return pdf_url
    except Exception as e:
        logger.debug(f"Unpaywall falló para {doi}: {e}")
        return None


# ---------------------------------------------------------------------------
# Europe PMC  (https://europepmc.org/RestfulWebService)
# ---------------------------------------------------------------------------

async def _europepmc_url(doi: str) -> Optional[str]:
    """Busca en Europe PMC por DOI y devuelve PDF URL si está disponible."""
    if not doi or doi.startswith("pubmed_"):
        return None
    search_url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query=DOI:{doi}&resultType=core&format=json&pageSize=1"
    )
    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            r = await client.get(search_url)
            if r.status_code != 200:
                return None
            results = r.json().get("resultList", {}).get("result", [])
            if not results:
                return None
            item = results[0]
            # Si tiene PMC ID, el texto completo es libre
            pmcid = item.get("pmcid")
            if pmcid:
                pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
                logger.info(f"Europe PMC encontró PDF para {doi} vía {pmcid}")
                return pdf_url
            # Verificar si tiene fullTextUrlList
            ft_list = item.get("fullTextUrlList", {}).get("fullTextUrl", [])
            for ft in ft_list:
                if ft.get("documentStyle") == "pdf" and ft.get("availability") in ("Open access", "Free"):
                    url = ft.get("url")
                    if url:
                        return url
    except Exception as e:
        logger.debug(f"Europe PMC falló para {doi}: {e}")
    return None


# ---------------------------------------------------------------------------
# Semantic Scholar  (openAccessPdf field)
# ---------------------------------------------------------------------------

async def _semantic_scholar_pdf_url(doi: str) -> Optional[str]:
    """Consulta Semantic Scholar por DOI y devuelve openAccessPdf si existe."""
    if not doi or doi.startswith("pubmed_") or doi.startswith("user_upload_"):
        return None
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf,title"
    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            oa = data.get("openAccessPdf") or {}
            pdf_url = oa.get("url")
            if pdf_url:
                logger.info(f"Semantic Scholar openAccessPdf para {doi}: {pdf_url}")
            return pdf_url
    except Exception as e:
        logger.debug(f"Semantic Scholar falló para {doi}: {e}")
        return None


# ---------------------------------------------------------------------------
# OpenAlex  (open_access.oa_url — muy rápido, cubre PMC + repositorios)
# ---------------------------------------------------------------------------

async def _openalex_url(doi: str) -> Optional[str]:
    """Consulta OpenAlex por DOI y devuelve open_access.oa_url si existe."""
    if not doi or doi.startswith("pubmed_") or doi.startswith("user_upload_"):
        return None
    url = f"https://api.openalex.org/works/doi:{doi}?select=open_access"
    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            r = await client.get(url, headers={"User-Agent": "mailto:surgical-system@example.com"})
            if r.status_code != 200:
                return None
            oa = r.json().get("open_access") or {}
            oa_url = oa.get("oa_url")
            if oa_url:
                logger.info(f"OpenAlex OA URL para {doi}: {oa_url}")
            return oa_url
    except Exception as e:
        logger.debug(f"OpenAlex falló para {doi}: {e}")
    return None


# ---------------------------------------------------------------------------
# CORE API  (https://core.ac.uk/services/api)  – sin clave, resultados limitados
# ---------------------------------------------------------------------------

async def _core_pdf_url(title: str) -> Optional[str]:
    """Busca en CORE por título y devuelve downloadUrl si hay PDF libre."""
    if not title:
        return None
    query = re.sub(r"[^\w\s]", "", title)[:120]
    url = f"https://api.core.ac.uk/v3/search/works?q={query}&limit=3"
    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            r = await client.get(url, headers={"Accept": "application/json"})
            if r.status_code != 200:
                return None
            results = r.json().get("results", [])
            for item in results:
                pdf = item.get("downloadUrl") or item.get("links", [{}])[0].get("url", "")
                if pdf and pdf.endswith(".pdf"):
                    logger.info(f"CORE encontró PDF para '{title[:60]}': {pdf}")
                    return pdf
    except Exception as e:
        logger.debug(f"CORE falló para '{title[:50]}': {e}")
    return None


# ---------------------------------------------------------------------------
# Descarga de PDF y extracción de texto
# ---------------------------------------------------------------------------

async def download_pdf(url: str, save_path: str) -> bool:
    """Descarga un PDF desde una URL y lo guarda en disco. Retorna True si OK."""
    try:
        async with httpx.AsyncClient(
            timeout=_DL_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SurgicalResearch/1.0; +https://github.com)"}
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return False
            content_type = r.headers.get("content-type", "")
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                # Verificar magic bytes
                if not r.content[:4] == b"%PDF":
                    logger.debug(f"URL no es PDF: {url} (content-type: {content_type})")
                    return False
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(r.content)
            logger.info(f"PDF descargado ({len(r.content)//1024} KB): {save_path}")
            return True
    except Exception as e:
        logger.debug(f"Error descargando PDF desde {url}: {e}")
        return False


def extract_text_from_pdf_path(pdf_path: str, max_chars: int = 15000) -> str:
    """Extrae texto de un PDF descargado usando pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
            if len(text) >= max_chars:
                break
        return text.strip()[:max_chars]
    except Exception as e:
        logger.error(f"Error extrayendo texto de {pdf_path}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Verificación rápida de disponibilidad OA (sin descargar PDF)
# ---------------------------------------------------------------------------

_OA_CHECK_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)

async def _check_oa_fast(doi: str) -> Optional[str]:
    """Consulta Unpaywall + OpenAlex en paralelo para ver si un DOI tiene acceso libre.
    Retorna la URL OA si está disponible, None si no. Timeout agresivo: no bloquea el pipeline."""
    if not doi or doi.startswith("pubmed_") or doi.startswith("user_upload_"):
        return None
    async def _unpaywall():
        try:
            async with httpx.AsyncClient(timeout=_OA_CHECK_TIMEOUT) as c:
                r = await c.get(f"https://api.unpaywall.org/v2/{doi}?email={_OA_EMAIL}")
                if r.status_code == 200:
                    best = r.json().get("best_oa_location") or {}
                    return best.get("url_for_pdf") or best.get("url")
        except Exception:
            pass
        return None

    async def _openalex():
        try:
            async with httpx.AsyncClient(timeout=_OA_CHECK_TIMEOUT) as c:
                r = await c.get(
                    f"https://api.openalex.org/works/doi:{doi}?select=open_access",
                    headers={"User-Agent": f"mailto:{_OA_EMAIL}"}
                )
                if r.status_code == 200:
                    oa = r.json().get("open_access") or {}
                    return oa.get("oa_url")
        except Exception:
            pass
        return None

    results = await asyncio.gather(_unpaywall(), _openalex(), return_exceptions=True)
    for r in results:
        if isinstance(r, str) and r:
            return r
    return None


async def check_oa_availability_batch(papers: list) -> list:
    """
    Para cada paper con DOI real, verifica si hay versión de acceso abierto.
    Añade campos 'oa_url' (str|None) y 'oa_available' (bool) a cada paper.
    Corre en paralelo con timeout agresivo — no bloquea si las APIs tardan.
    """
    async def _check_one(paper: dict) -> dict:
        doi = paper.get("doi", "")
        oa_url = await _check_oa_fast(doi)
        paper = dict(paper)
        paper["oa_url"] = oa_url
        paper["oa_available"] = bool(oa_url)
        return paper

    updated = await asyncio.gather(
        *[_check_one(p) for p in papers],
        return_exceptions=True
    )
    result = []
    for i, r in enumerate(updated):
        if isinstance(r, Exception):
            result.append(papers[i])
        else:
            result.append(r)
    return result


# ---------------------------------------------------------------------------
# Función principal orquestadora
# ---------------------------------------------------------------------------

async def fetch_free_fulltext(
    doi: str,
    title: str = "",
    save_dir: str = "static/downloads/fulltext"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Intenta obtener el texto completo de un paper de forma gratuita y legal.
    Fuentes (todas legales): Unpaywall · Semantic Scholar OA · Europe PMC · OpenAlex · CORE.

    Returns:
        (pdf_path, full_text) — ambos None si no se encontró ninguna fuente libre.
    """
    # Intentar todas las fuentes en paralelo para velocidad
    pdf_url_results = await asyncio.gather(
        _unpaywall_url(doi),
        _semantic_scholar_pdf_url(doi),
        _europepmc_url(doi),
        _openalex_url(doi),
        return_exceptions=True
    )

    pdf_url: Optional[str] = None
    for result in pdf_url_results:
        if isinstance(result, str) and result.startswith("http"):
            pdf_url = result
            break

    # Si ninguna fuente por DOI funcionó, intentar CORE por título
    if not pdf_url and title:
        pdf_url = await _core_pdf_url(title)

    if not pdf_url:
        return None, None

    # Descargar el PDF
    safe_doi = re.sub(r"[^\w-]", "_", doi or title[:30])
    save_path = os.path.join(save_dir, f"{safe_doi}.pdf")

    downloaded = await download_pdf(pdf_url, save_path)
    if not downloaded:
        return None, None

    # Extraer texto en un hilo aparte: pypdf es síncrono y bloquearía el event loop
    # (congelando el stream SSE y aparentando un cuelgue durante el enriquecimiento).
    full_text = await asyncio.to_thread(extract_text_from_pdf_path, save_path)
    return save_path, full_text if full_text else None


async def enrich_papers_with_fulltext(
    papers: list,
    event_queue,
    run_id: str,
    max_papers: int = 10
) -> list:
    """
    Para cada paper de la lista, intenta obtener el texto completo libre.
    Si se obtiene, reemplaza/enriquece el abstract con los primeros 1500 chars del texto.
    Procesa hasta max_papers papers con DOI.
    """
    from app.agents.base import BaseAgent

    class FulltextAgent(BaseAgent):
        def __init__(self):
            super().__init__(
                name="Agente Descargador de Texto Completo",
                role="Recuperador",
                color="#f59e0b",
                icon="📄"
            )

    agent = FulltextAgent()
    save_dir = f"static/downloads/{run_id}/fulltext"
    os.makedirs(save_dir, exist_ok=True)

    enriched = 0
    tasks_with_index = [
        (i, p) for i, p in enumerate(papers)
        if p.get("doi") and not p["doi"].startswith("pubmed_") and not p["doi"].startswith("user_upload_")
    ][:max_papers]

    if not tasks_with_index:
        return papers

    await event_queue.put(agent.format_log(
        f"Buscando texto completo libre en **Unpaywall**, **Semantic Scholar OA**, "
        f"**Europe PMC** y **CORE** para los {len(tasks_with_index)} papers con DOI...",
        "search"
    ))

    async def _enrich_one(idx: int, paper: dict) -> Tuple[int, dict]:
        try:
            pdf_path, full_text = await asyncio.wait_for(
                fetch_free_fulltext(
                    doi=paper.get("doi", ""),
                    title=paper.get("title", ""),
                    save_dir=save_dir
                ),
                timeout=18.0
            )
            if full_text:
                existing_abstract = paper.get("abstract", "")
                if len(full_text) > len(existing_abstract) + 200:
                    paper = dict(paper)
                    paper["abstract"] = full_text[:1500]
                    paper["fulltext_path"] = pdf_path
                    paper["has_fulltext"] = True
        except Exception:
            pass  # timeout or network error — use paper as-is
        return idx, paper

    results = await asyncio.gather(
        *[_enrich_one(i, p) for i, p in tasks_with_index],
        return_exceptions=True
    )

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error enriqueciendo paper: {result}")
            continue
        idx, enriched_paper = result
        papers[idx] = enriched_paper
        if enriched_paper.get("has_fulltext"):
            enriched += 1

    await event_queue.put(agent.format_log(
        f"Texto completo recuperado para **{enriched}/{len(tasks_with_index)}** papers. "
        f"{'Los abstracts fueron reemplazados por el texto real del paper.' if enriched else 'Las fuentes libres no retornaron PDFs descargables para esta búsqueda (papers de pago sin versión OA).'}",
        "search"
    ))

    return papers
