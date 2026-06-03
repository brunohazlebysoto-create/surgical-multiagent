import logging
import os
import base64
from typing import Optional
from docx import Document
from pptx import Presentation
from pypdf import PdfReader
from app.agents.base import call_gemini

logger = logging.getLogger("document_parser")

def extract_text_from_pdf(filepath: str) -> str:
    """Extrae texto de un archivo PDF usando pypdf."""
    try:
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Error extrayendo texto de PDF {filepath}: {e}")
        raise e

def extract_text_from_docx(filepath: str) -> str:
    """Extrae texto de un archivo de Word (.docx) usando python-docx."""
    try:
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        # También extraer texto de tablas
        table_text = []
        for table in doc.tables:
            for row in table.rows:
                row_cells = [cell.text for cell in row.cells if cell.text]
                if row_cells:
                    table_text.append(" | ".join(row_cells))
        return "\n".join(paragraphs + table_text).strip()
    except Exception as e:
        logger.error(f"Error extrayendo texto de DOCX {filepath}: {e}")
        raise e

def extract_text_from_pptx(filepath: str) -> str:
    """Extrae texto de una presentación de PowerPoint (.pptx) usando python-pptx."""
    try:
        prs = Presentation(filepath)
        text = ""
        for i, slide in enumerate(prs.slides):
            text += f"\n--- Diapositiva {i+1} ---\n"
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    text += shape.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Error extrayendo texto de PPTX {filepath}: {e}")
        raise e

async def generate_document_abstract(text: str, filename: str, pdf_base64: Optional[str] = None) -> str:
    """
    Toma el texto completo extraído (o el PDF codificado en Base64 para modo multimodal)
    y usa Gemini para generar un resumen estructurado (Abstract) médico/quirúrgico de alta calidad.
    """
    if pdf_base64:
        prompt = f"""
        Eres un transcriptor y redactor médico especializado en cirugía infantil y medicina basada en evidencia.
        Analiza el documento PDF clínico adjunto (Archivo: {filename}).
        El usuario requiere que no te limites al resumen; debes leer detalladamente todo el contenido del documento, analizando minuciosamente cada tabla, gráfico, figura, diagrama e imagen clínica presente en el PDF.
        
        Por favor, genera un resumen/síntesis estructurado extremadamente riguroso y detallado (Abstract ampliado) de máximo 600 palabras que incluya:
        1. **Objetivo y Diseño**: Objetivo principal, tipo de estudio y el contexto clínico detallado.
        2. **Población Pediátrica**: Detalles específicos de los pacientes (edad promedio/grupos etarios, peso, criterios de inclusión/exclusión y severidad de la patología).
        3. **Detalles Quirúrgicos/Médicos y Figuras/Imágenes**: Describe con precisión técnica las imágenes diagnósticas (radiografías, ecografías, TAC, etc.), diagramas quirúrgicos, pasos de la intervención, y los gráficos de resultados (por ejemplo, curvas de aprendizaje, diagramas de barras, etc.).
        4. **Tablas de Datos y Resultados**: Transcribe los datos y estadísticas clave de las tablas del documento (éxito %, complicaciones %, p-values, odds ratios, etc.).
        5. **Conclusiones Clínicas**: Hallazgos clave aplicables directamente en el quirófano infantil.
        
        Este resumen enriquecido servirá como la base de conocimiento completa de este paper para un panel de 15 agentes de IA. No omitas datos numéricos ni hallazgos visuales.
        """
        try:
            logger.info(f"Llamando a Gemini en modo MULTIMODAL para el PDF: {filename}")
            summary = await call_gemini(prompt, temperature=0.15, inline_data={"mimeType": "application/pdf", "data": pdf_base64})
            return summary
        except Exception as e:
            logger.error(f"Error generando resumen multimodal para {filename}: {e}. Intentando fallback con texto extraído.")

    if not text:
        return "El archivo no contiene texto legible."
        
    # Limitar texto de entrada si es absurdamente largo por seguridad de tokens (ej: 30k caracteres)
    input_text = text[:30000]
    
    prompt = f"""
    Eres un transcriptor y redactor médico especializado en cirugía infantil y medicina basada en evidencia.
    Analiza el siguiente documento clínico subido por el usuario (Archivo: {filename}). 
    El usuario requiere que no te limites al resumen; debes leer detalladamente todo el contenido del texto, extrayendo información de las tablas, gráficos, figuras e imágenes descritas en el texto.
    
    Texto completo del documento:
    ---
    {input_text}
    ---
    
    Genera un resumen/síntesis estructurado extremadamente riguroso y detallado (Abstract ampliado) de máximo 600 palabras que incluya:
    1. **Objetivo y Diseño**: Objetivo principal, tipo de estudio y el contexto clínico detallado.
    2. **Población Pediátrica**: Detalles específicos de los pacientes (edad promedio/grupos etarios, peso, criterios de inclusión/exclusión y severidad de la patología).
    3. **Detalles Quirúrgicos/Médicos y Figuras**: Pasos exactos de la intervención quirúrgica (colocación de puertos, instrumental, reparos anatómicos) y descripción detallada de hallazgos en imágenes diagnósticas, gráficos de supervivencia, curvas de aprendizaje o figuras de resultados mencionadas.
    4. **Tablas de Datos y Resultados**: Transcribe los datos clave de las tablas (porcentajes de éxito, tasas de complicaciones estadísticas en %, tiempos quirúrgicos, sangrado estimado, etc.).
    5. **Conclusiones Clínicas**: Hallazgos clave aplicables directamente en el quirófano infantil.
    
    Este resumen enriquecido será utilizado por un panel de 15 agentes de IA para un meta-análisis GRADE y redacción de consensos de alta precisión. No resumas por encima, conserva los datos numéricos y comparativos exactos.
    """
    
    try:
        summary = await call_gemini(prompt, temperature=0.15)
        return summary
    except Exception as e:
        logger.error(f"Error generando resumen de texto para {filename} con Gemini: {e}")
        # Fallback simple
        return f"Documento subido '{filename}'. Contenido de texto extraído: {text[:500]}..."

async def parse_uploaded_document(filepath: str, filename: str) -> dict:
    """
    Orquesta la extracción del texto y la generación del abstract/resumen.
    Devuelve un diccionario estructurado como un 'paper'.
    """
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    pdf_base64 = None
    
    logger.info(f"Procesando archivo subido: {filename} ({ext})")
    
    if ext == ".pdf":
        # Extraer texto de respaldo por si falla el modo multimodal
        try:
            text = extract_text_from_pdf(filepath)
        except Exception as err:
            logger.warning(f"No se pudo extraer texto de PDF {filename}: {err}")
            text = ""
            
        # Codificar en Base64 para multimodal si tiene tamaño adecuado (<15MB)
        try:
            file_size = os.path.getsize(filepath)
            if file_size <= 15 * 1024 * 1024:
                with open(filepath, "rb") as f:
                    pdf_bytes = f.read()
                pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
                logger.info(f"PDF {filename} codificado en Base64 ({len(pdf_base64)} caracteres) para análisis multimodal.")
            else:
                logger.warning(f"El archivo {filename} ({file_size} bytes) excede el límite de 15MB para envío multimodal directo.")
        except Exception as e:
            logger.error(f"Error codificando PDF {filename} a Base64: {e}")
            
    elif ext == ".docx":
        text = extract_text_from_docx(filepath)
    elif ext == ".pptx":
        text = extract_text_from_pptx(filepath)
    else:
        raise ValueError(f"Extensión de archivo no soportada: {ext}")
        
    abstract = await generate_document_abstract(text, filename, pdf_base64)
    
    # Simular la estructura de paper científico
    return {
        "title": filename,
        "authors": "Usuario (Documento Subido)",
        "journal": "Documento Adjunto Local",
        "year": 2026,
        "doi": f"user_upload_{uuid_hash(filename)}",
        "abstract": abstract
    }

def uuid_hash(name: str) -> str:
    """Genera un hash simple de 8 caracteres a partir del nombre del archivo."""
    import hashlib
    return hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
