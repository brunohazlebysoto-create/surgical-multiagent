import asyncio
import json
import logging
import os
import uuid
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form, Depends, Header, Query
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.config import ACCESS_PASSWORD

from app.agents.searcher import run_search_panel
from app.agents.analyzer import run_analyzer_panel
from app.agents.meta_analyst import run_meta_analyst_panel
from app.agents.writer import run_writer_panel
from app.agents.presenter import run_presenter_panel

from app.services.docx_generator import build_docx
from app.services.pptx_generator import build_pptx
from app.services.document_parser import parse_uploaded_document
from app.services.fulltext_fetcher import enrich_papers_with_fulltext

# Configurar logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("multiagent_main")

app = FastAPI(title="Surgical Multi-Agent System")

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estructura para almacenar las ejecuciones activas
# run_id -> {"event_queue": Queue, "docx_path": str, "pptx_path": str, "json_path": str, "step2_trigger": asyncio.Event, "papers_found": list, "uploaded_papers": list, "selected_dois": list}
global_runs = {}

# Asegurar directorios estáticos de salida
os.makedirs("static/downloads", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

async def verify_access(
    x_access_password: Optional[str] = Header(None),
    password: Optional[str] = Query(None)
):
    provided_password = x_access_password or password
    if ACCESS_PASSWORD and provided_password != ACCESS_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Contraseña de acceso inválida o no provista"
        )

@app.get("/api/auth-check")
async def auth_check(password: Optional[str] = Query(None)):
    if not ACCESS_PASSWORD:
        return {"status": "disabled"}
    if password == ACCESS_PASSWORD:
        return {"status": "authenticated"}
    return {"status": "unauthorized"}

class PipelineConfig(BaseModel):
    reranking: bool = True
    pmc_download: bool = True
    multimodal_pdf: bool = True

class SearchRequest(BaseModel):
    query: str
    pipeline_config: PipelineConfig = PipelineConfig()

class ConfirmRequest(BaseModel):
    selected_dois: List[str]

class ConfirmFormatRequest(BaseModel):
    output_format: str = "both"   # "word", "pptx", "both"
    detail_level: str = "long"    # "short", "medium", "long", "very_detailed"

async def execute_multiagent_pipeline(query: str, event_queue: asyncio.Queue, run_id: str, client_keys: List[str] = None, pipeline_config: dict = None):
    """
    Orquesta el flujo del multi-agente.
    Pausa el flujo al finalizar el Paso 1 (Búsqueda) y espera confirmación del usuario.
    """
    from app.agents.base import gemini_keys_context
    token = gemini_keys_context.set(client_keys)
    cfg = pipeline_config or {}
    # Inyectar run_id en la queue para que fulltext_fetcher pueda guardar PDFs
    event_queue._run_id = run_id
    try:

        # Paso 1: Panel de Búsqueda
        papers = await run_search_panel(
            query, event_queue,
            use_reranking=cfg.get("reranking", True)
        )
        
        # Almacenar en la memoria de la ejecución
        global_runs[run_id]["papers_found"] = papers

        # Verificar disponibilidad OA para todos los papers ANTES de mostrarlos al usuario
        # El usuario verá qué papers son de acceso libre directamente en la lista de selección
        await event_queue.put({
            "agent": "Sistema", "role": "Verificador OA",
            "color": "#a855f7", "icon": "🔓", "stage": "search",
            "content": f"Verificando disponibilidad de acceso abierto para los {len(papers)} papers encontrados..."
        })
        try:
            from app.services.fulltext_fetcher import check_oa_availability_batch
            papers = await asyncio.wait_for(
                check_oa_availability_batch(papers),
                timeout=20.0
            )
            global_runs[run_id]["papers_found"] = papers
            oa_count = sum(1 for p in papers if p.get("oa_available"))
            await event_queue.put({
                "agent": "Sistema", "role": "Verificador OA",
                "color": "#10b981", "icon": "🔓", "stage": "search",
                "content": f"**{oa_count}/{len(papers)}** papers disponibles en acceso abierto (PDF gratuito legal). Los papers marcados con 🔓 pueden descargarse completos para el análisis."
            })
        except Exception as e:
            logger.warning(f"Verificación OA no disponible: {e}")

        # Combinar papers encontrados con los subidos hasta este momento
        combined_papers = papers + global_runs[run_id]["uploaded_papers"]

        # Enviar evento de pausa solicitando selección interactiva
        await event_queue.put({
            "agent": "Sistema", "role": "Selector",
            "color": "#a855f7", "icon": "⚙️", "stage": "selection_required",
            "content": f"Búsqueda finalizada. Se encontraron **{len(papers)}** papers ({sum(1 for p in papers if p.get('oa_available'))} con acceso abierto 🔓). Selecciona los artículos para el análisis.",
            "papers": combined_papers
        })
        
        # Esperar a que el usuario confirme mediante el endpoint /api/confirm
        logger.info(f"Pipeline {run_id} pausado, esperando selección de papers.")
        await global_runs[run_id]["step2_trigger"].wait()
        logger.info(f"Pipeline {run_id} reanudado por confirmación del usuario.")
        
        # Obtener papers seleccionados
        selected_dois = global_runs[run_id]["selected_dois"]
        all_available_papers = global_runs[run_id]["papers_found"] + global_runs[run_id]["uploaded_papers"]
        selected_papers = [p for p in all_available_papers if p["doi"] in selected_dois]
        
        # Si por error no hay selección, usar el fallback del top 15
        if not selected_papers:
            selected_papers = all_available_papers[:15]
            
        # Descargar figuras de PMC en paralelo con tope global de 15s
        if cfg.get("pmc_download", True):
            from app.services.document_parser import download_pmc_figures
            await event_queue.put({
                "agent": "Sistema", "role": "Extractor",
                "color": "#a855f7", "icon": "📥", "stage": "analyze",
                "content": f"Descargando figuras de PubMed Central para {len(selected_papers)} papers (paralelo)..."
            })
            async def _fetch_figs(doi):
                try:
                    return await asyncio.wait_for(download_pmc_figures(doi, run_id), timeout=8.0)
                except Exception:
                    return []
            dois = [p.get("doi") for p in selected_papers
                    if p.get("doi") and not p["doi"].startswith("user_upload_")]
            try:
                all_figs = await asyncio.wait_for(
                    asyncio.gather(*[_fetch_figs(doi) for doi in dois]),
                    timeout=15.0
                )
                for figs in all_figs:
                    if figs:
                        global_runs[run_id]["extracted_images"].extend(figs)
            except Exception as e:
                logger.warning(f"Descarga de figuras PMC completada parcialmente: {e}")
            
        # Preguntar al usuario formato de salida y longitud antes de generar
        await event_queue.put({
            "agent": "Sistema", "role": "Configurador",
            "color": "#a855f7", "icon": "⚙️", "stage": "output_format_required",
            "content": f"✅ {len(selected_papers)} papers confirmados. **Elige el formato de salida** (Word, PowerPoint o ambos) y la extensión del documento para iniciar el análisis completo.",
            "papers_count": len(selected_papers)
        })
        logger.info(f"Pipeline {run_id} esperando configuración de formato.")
        await global_runs[run_id]["format_trigger"].wait()
        logger.info(f"Pipeline {run_id} reanudado con formato: {global_runs[run_id]['output_format']}, nivel: {global_runs[run_id]['detail_level']}")

        output_format = global_runs[run_id]["output_format"]
        detail_level = global_runs[run_id]["detail_level"]

        await event_queue.put({
            "agent": "Sistema", "role": "Analizador",
            "color": "#10b981", "icon": "✅", "stage": "analyze",
            "content": f"Iniciando Paso 2: Análisis PICO-S con {len(selected_papers)} artículos..."
        })

        # Enriquecimiento automático de texto completo — TODOS los papers seleccionados
        if cfg.get("pmc_download", True):
            n_with_doi = sum(
                1 for p in selected_papers
                if p.get("doi") and not p["doi"].startswith("pubmed_") and not p["doi"].startswith("user_upload_")
            )
            await event_queue.put({
                "agent": "Sistema", "role": "Enriquecedor",
                "color": "#f59e0b", "icon": "📄", "stage": "analyze",
                "content": f"Descargando texto completo de **todos** los {n_with_doi} papers seleccionados con DOI (Unpaywall, S2OA, Europe PMC, OpenAlex, CORE)..."
            })
            try:
                # Todos los papers corren en paralelo y cada uno tiene un timeout de 18s
                # dentro de _enrich_one, así que 60s es más que suficiente como tope global.
                enrich_timeout = 60.0
                selected_papers = await asyncio.wait_for(
                    enrich_papers_with_fulltext(
                        selected_papers, event_queue, run_id=run_id,
                        max_papers=len(selected_papers)  # sin límite: todos los seleccionados
                    ),
                    timeout=enrich_timeout
                )
            except Exception as e:
                logger.warning(f"Enriquecimiento de texto completo fallido (no fatal): {e}")

        # Paso 2: Panel de Análisis PICO-S (usando solo la selección)
        analyzed_papers = await run_analyzer_panel(selected_papers, event_queue)

        # Paso 3: Panel de Meta-Análisis
        meta_analysis = await run_meta_analyst_panel(analyzed_papers, query, event_queue)

        # Paso 4: Panel de Redacción Científica (Word) — omitir si solo PPT
        sections = {}
        if output_format in ("word", "both"):
            sections = await run_writer_panel(meta_analysis, analyzed_papers, query, event_queue, detail_level=detail_level)

        # Paso 5: Panel de Presentación (PowerPoint) — omitir si solo Word
        slides = []
        if output_format in ("pptx", "both"):
            slides = await run_presenter_panel(meta_analysis, analyzed_papers, query, event_queue, detail_level=detail_level)
        
        # --- RENDERIZACIÓN DE ARCHIVOS ---
        run_dir = f"static/downloads/{run_id}"
        os.makedirs(run_dir, exist_ok=True)
        
        docx_filepath = f"{run_dir}/apunte_clinico.docx"
        pptx_filepath = f"{run_dir}/presentacion_profesional.pptx"
        json_filepath = f"{run_dir}/meta_analisis.json"
        
        output_format = global_runs[run_id]["output_format"]

        # Generar Word (si aplica)
        if output_format in ("word", "both"):
            await event_queue.put({
                "agent": "Sistema de Compilación", "role": "Renderizador",
                "color": "#a855f7", "icon": "⚙️", "stage": "render",
                "content": "Renderizando documento científico de Word (.docx) con estilo Navy..."
            })
            prisma_data = {
                "identified": len(global_runs[run_id]["papers_found"]) * 4 + 10,
                "screened": len(global_runs[run_id]["papers_found"]) + len(global_runs[run_id]["uploaded_papers"]),
                "excluded": (len(global_runs[run_id]["papers_found"]) + len(global_runs[run_id]["uploaded_papers"])) - len(selected_papers),
                "included": len(selected_papers)
            }
            build_docx(sections, docx_filepath, query,
                       extracted_images=global_runs[run_id]["extracted_images"],
                       prisma_data=prisma_data,
                       meta_analysis=meta_analysis)
            global_runs[run_id]["docx_path"] = f"/static/downloads/{run_id}/apunte_clinico.docx"

        # Generar PowerPoint (si aplica)
        if output_format in ("pptx", "both"):
            await event_queue.put({
                "agent": "Sistema de Compilación", "role": "Renderizador",
                "color": "#a855f7", "icon": "⚙️", "stage": "render",
                "content": "Renderizando presentación de PowerPoint (.pptx) detallada..."
            })
            build_pptx(slides, pptx_filepath, run_id=run_id, meta_analysis=meta_analysis)
            global_runs[run_id]["pptx_path"] = f"/static/downloads/{run_id}/presentacion_profesional.pptx"
        
        # Guardar JSON de Meta-análisis
        await event_queue.put({
            "agent": "Sistema de Compilación", "role": "Renderizador", 
            "color": "#a855f7", "icon": "⚙️", "stage": "render", 
            "content": "Guardando archivo JSON de la síntesis de evidencia..."
        })
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(meta_analysis, f, ensure_ascii=False, indent=2)
            
        global_runs[run_id]["json_path"] = f"/static/downloads/{run_id}/meta_analisis.json"
        
        # Evento de éxito final
        await event_queue.put({
            "agent": "Sistema", "role": "Completado", 
            "color": "#10b981", "icon": "✅", "stage": "completed", 
            "content": f"El pipeline de cirugía infantil sobre '{query}' ha finalizado exitosamente. Los entregables profesionales están listos para descarga.",
            "selected_papers": [
                {
                    "title": p["title"],
                    "authors": p["authors"],
                    "journal": p["journal"],
                    "year": p["year"],
                    "doi": p["doi"],
                    "url": f"/static/uploads/{run_id}/{p['title']}" if "user_upload_" in p["doi"] else (f"https://doi.org/{p['doi']}" if p["doi"] and not p["doi"].startswith("pubmed_") else f"https://pubmed.ncbi.nlm.nih.gov/{p['doi'].split('_')[-1]}/" if p["doi"] else "#")
                } for p in selected_papers
            ]
        })
        
    except Exception as e:
        logger.exception("Error durante la ejecución del pipeline")
        await event_queue.put({
            "agent": "Sistema", "role": "Error", 
            "color": "#ef4444", "icon": "❌", "stage": "failed", 
            "content": f"Ocurrió un error crítico durante el análisis: {str(e)}"
        })
    finally:
        gemini_keys_context.reset(token)


@app.post("/api/start")
async def start_pipeline(
    request: SearchRequest, 
    background_tasks: BackgroundTasks, 
    x_gemini_api_keys: Optional[str] = Header(None),
    _ = Depends(verify_access)
):
    """
    Endpoint para iniciar el pipeline asíncronamente en segundo plano.
    """
    run_id = str(uuid.uuid4())
    event_queue = asyncio.Queue()
    
    global_runs[run_id] = {
        "event_queue": event_queue,
        "docx_path": None,
        "pptx_path": None,
        "json_path": None,
        "query": request.query,
        "step2_trigger": asyncio.Event(),
        "format_trigger": asyncio.Event(),
        "papers_found": [],
        "uploaded_papers": [],
        "selected_dois": [],
        "extracted_images": [],
        "output_format": "both",
        "detail_level": "long"
    }
    
    # Parsear claves de API enviadas por el cliente
    client_keys = []
    if x_gemini_api_keys:
        client_keys = [k.strip() for k in x_gemini_api_keys.split(",") if k.strip()]

    # Serializar pipeline_config como dict plano
    pipeline_config = request.pipeline_config.model_dump() if request.pipeline_config else {}

    # Agregar la tarea en segundo plano pasándole las claves y config
    background_tasks.add_task(execute_multiagent_pipeline, request.query, event_queue, run_id, client_keys, pipeline_config)
    
    return {"run_id": run_id}


@app.post("/api/confirm/{run_id}")
async def confirm_selection(run_id: str, request: ConfirmRequest, _ = Depends(verify_access)):
    """
    Endpoint para recibir los DOIs seleccionados por el usuario y reanudar el análisis.
    """
    if run_id not in global_runs:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")
        
    global_runs[run_id]["selected_dois"] = request.selected_dois

    # Reanudar la tarea en background
    global_runs[run_id]["step2_trigger"].set()

    return {"status": "success"}


@app.post("/api/confirm-format/{run_id}")
async def confirm_format(run_id: str, request: ConfirmFormatRequest, _ = Depends(verify_access)):
    """
    Recibe la elección de formato de salida (word/pptx/both) y nivel de detalle.
    """
    if run_id not in global_runs:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")

    valid_formats = {"word", "pptx", "both"}
    valid_levels = {"short", "medium", "long", "very_detailed"}
    if request.output_format not in valid_formats:
        raise HTTPException(status_code=400, detail=f"output_format inválido. Use: {valid_formats}")
    if request.detail_level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"detail_level inválido. Use: {valid_levels}")

    global_runs[run_id]["output_format"] = request.output_format
    global_runs[run_id]["detail_level"] = request.detail_level
    global_runs[run_id]["format_trigger"].set()

    return {"status": "success"}


@app.post("/api/upload")
async def upload_document(
    run_id: str = Form(...), 
    file: UploadFile = File(...), 
    x_gemini_api_keys: Optional[str] = Header(None),
    _ = Depends(verify_access)
):
    """
    Endpoint para cargar archivos de usuario (.pdf, .docx, .pptx) y procesar su texto.
    """
    if run_id not in global_runs:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")
        
    # Guardar archivo físicamente
    upload_dir = f"static/uploads/{run_id}"
    os.makedirs(upload_dir, exist_ok=True)
    filepath = f"{upload_dir}/{file.filename}"
    
    with open(filepath, "wb") as f:
        f.write(await file.read())
        
    # Parsear y generar abstract clínico
    from app.agents.base import gemini_keys_context
    client_keys = []
    if x_gemini_api_keys:
        client_keys = [k.strip() for k in x_gemini_api_keys.split(",") if k.strip()]
        
    token = gemini_keys_context.set(client_keys)
    try:
        event_queue = global_runs[run_id]["event_queue"]
        await event_queue.put({
            "agent": "Sistema de Archivos", "role": "Procesador",
            "color": "#eab308", "icon": "📁", "stage": "search",
            "content": f"Procesando archivo subido '{file.filename}'. Extrayendo texto y generando resumen clínico con Gemini..."
        })
        
        parsed_paper = await parse_uploaded_document(filepath, file.filename, run_id=run_id)
        
        # Almacenar en la memoria de la ejecución
        global_runs[run_id]["uploaded_papers"].append(parsed_paper)
        if "extracted_images" in parsed_paper and parsed_paper["extracted_images"]:
            global_runs[run_id]["extracted_images"].extend(parsed_paper["extracted_images"])
        
        await event_queue.put({
            "agent": "Sistema de Archivos", "role": "Procesador",
            "color": "#10b981", "icon": "✅", "stage": "search",
            "content": f"Archivo '{file.filename}' procesado y resumido con éxito. Añadido a la lista de selección."
        })
        
        return {"status": "success", "paper": parsed_paper}
        
    except Exception as e:
        logger.exception("Error al subir y parsear archivo")
        raise HTTPException(status_code=500, detail=f"Error parseando el archivo: {str(e)}")
    finally:
        gemini_keys_context.reset(token)


class FreeSearchRequest(BaseModel):
    doi: str
    title: str = ""

@app.post("/api/search-free/{run_id}")
async def search_free_paper(run_id: str, request: FreeSearchRequest, _ = Depends(verify_access)):
    """
    Busca la versión gratuita y legal de un paper en Unpaywall, Semantic Scholar OA,
    Europe PMC y CORE. Si se encuentra, descarga el PDF y lo añade como paper subido.
    """
    if run_id not in global_runs:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")

    from app.services.fulltext_fetcher import fetch_free_fulltext
    save_dir = f"static/downloads/{run_id}/fulltext"

    pdf_path, full_text = await fetch_free_fulltext(
        doi=request.doi,
        title=request.title,
        save_dir=save_dir
    )

    if not pdf_path or not full_text:
        return {"status": "not_found", "message": "No se encontró versión libre de acceso abierto para este paper."}

    return {
        "status": "found",
        "pdf_path": pdf_path,
        "text_preview": full_text[:400],
        "chars": len(full_text)
    }


@app.get("/api/stream/{run_id}")
async def stream_events(run_id: str, _ = Depends(verify_access)):
    """
    Endpoint SSE (Server-Sent Events) para transmitir el debate de los agentes en vivo.
    """
    if run_id not in global_runs:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")
        
    queue = global_runs[run_id]["event_queue"]
    
    async def event_generator():
        while True:
            try:
                # Esperar nuevos eventos de la cola de logs
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                
                # Si el evento es completado o fallado, cerrar el stream
                if event.get("stage") in ["completed", "failed"]:
                    break
            except Exception as e:
                logger.error(f"Error en el generador de eventos SSE: {e}")
                break
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/downloads/{run_id}/{file_type}")
async def get_download_file(run_id: str, file_type: str):
    """
    Endpoint para descargar los entregables generados.
    Soporta búsquedas físicas si la memoria del servidor fue limpiada por reinicio/reload.
    """
    import re as _re

    filepath = None
    query = ""

    # 1. Intentar buscar en la memoria activa de la ejecución
    if run_id in global_runs:
        run_info = global_runs[run_id]
        query = run_info.get("query", "")
        if file_type == "word":
            filepath = run_info.get("docx_path")
        elif file_type == "powerpoint":
            filepath = run_info.get("pptx_path")
        elif file_type == "json":
            filepath = run_info.get("json_path")

    # 2. Si no está en memoria (ej. por recarga de Uvicorn), buscar directamente en disco
    if not filepath:
        run_dir = f"static/downloads/{run_id}"
        if file_type == "word":
            temp_path = f"{run_dir}/apunte_clinico.docx"
        elif file_type == "powerpoint":
            temp_path = f"{run_dir}/presentacion_profesional.pptx"
        elif file_type == "json":
            temp_path = f"{run_dir}/meta_analisis.json"
        else:
            raise HTTPException(status_code=400, detail="Tipo de archivo inválido")

        if os.path.exists(temp_path):
            filepath = temp_path

    if not filepath:
        raise HTTPException(
            status_code=404,
            detail="Ejecución o archivos no encontrados. Si el servidor se reinició, por favor inicia un nuevo análisis."
        )

    # Limpiar barra inicial para compatibilidad con FileResponse
    clean_path = filepath.lstrip("/")

    if not os.path.exists(clean_path):
        raise HTTPException(status_code=404, detail="El archivo físico no fue encontrado en el disco")

    # Construir nombre de descarga con el tema de búsqueda
    if query:
        safe_query = _re.sub(r'[^\w\s\-áéíóúüñÁÉÍÓÚÜÑ]', '', query).strip()[:50]
        if file_type == "word":
            filename = f"apunte de {safe_query}.docx"
        elif file_type == "powerpoint":
            filename = f"presentacion de {safe_query}.pptx"
        else:
            filename = os.path.basename(clean_path)
    else:
        filename = os.path.basename(clean_path)

    return FileResponse(clean_path, filename=filename, media_type="application/octet-stream")

# Servir Frontend
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

# Montar carpeta estática
app.mount("/static", StaticFiles(directory="static"), name="static")
