import os
import re
import logging
from typing import Dict
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

logger = logging.getLogger("docx_generator")

NAVY_COLOR = RGBColor(15, 44, 89)      # #0F2C59
SLATE_COLOR = RGBColor(70, 80, 95)     # #46505F
TEXT_COLOR = RGBColor(33, 37, 41)      # #212529

def set_cell_background(cell, color_hex: str):
    """Establece el color de fondo de una celda en Word."""
    shading_xml = f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>'
    cell._tc.get_or_add_tcPr().append(parse_xml(shading_xml))

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Aplica márgenes internos (padding) a una celda para mejor legibilidad."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for margin_name, val in [('w:top', top), ('w:bottom', bottom), ('w:left', left), ('w:right', right)]:
        node = OxmlElement(margin_name)
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def parse_inline_formatting(paragraph, text: str):
    """Mapea negritas básicas en Markdown (**texto**) a runs de python-docx."""
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            bold_text = part[2:-2]
            run = paragraph.add_run(bold_text)
            run.bold = True
        else:
            paragraph.add_run(part)

def add_styled_table(doc, headers: list, rows: list):
    """Genera una tabla con estilo quirúrgico Navy y celdas con padding."""
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.autofit = False
    
    # 1. Cabecera (Navy con texto blanco)
    hdr_cells = table.rows[0].cells
    for i, header in enumerate(headers):
        hdr_cells[i].text = header
        set_cell_background(hdr_cells[i], "0F2C59")
        set_cell_margins(hdr_cells[i], top=140, bottom=140, left=180, right=180)
        
        # Formato de texto de cabecera
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.name = 'Arial'
            run.font.size = Pt(10)

    # 2. Filas de datos (Zebra striping alternando fondo gris claro)
    for r_idx, row_data in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        bg_color = "F8F9FA" if r_idx % 2 == 0 else "FFFFFF"
        
        for c_idx, cell_value in enumerate(row_data):
            # Prevenir desbordamiento de columnas si la fila tiene más celdas que la cabecera
            if c_idx >= len(headers):
                continue
                
            row_cells[c_idx].text = cell_value
            set_cell_background(row_cells[c_idx], bg_color)
            set_cell_margins(row_cells[c_idx], top=100, bottom=100, left=150, right=150)
            
            p = row_cells[c_idx].paragraphs[0]
            # Procesar posibles negritas dentro de las celdas
            p.text = "" # limpiar texto plano
            parse_inline_formatting(p, cell_value)
            
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(9.5)
                run.font.color.rgb = TEXT_COLOR
                
    doc.add_paragraph() # Espacio post-tabla

def parse_markdown_to_docx(doc, md_text: str):
    """
    Parsea texto Markdown básico a párrafos y tablas estructuradas en el documento de Word.
    """
    lines = md_text.split('\n')
    in_table = False
    table_headers = []
    table_rows = []
    
    for line in lines:
        line_strip = line.strip()
        
        # 1. Procesar Tablas
        if line_strip.startswith('|'):
            if not in_table:
                in_table = True
                table_headers = [c.strip() for c in line_strip.split('|')[1:-1]]
                table_rows = []
            else:
                # Omitir la línea divisoria del encabezado (ej: |---|---|)
                if re.match(r'^\|[\s:-|]+$', line_strip):
                    continue
                row_cells = [c.strip() for c in line.split('|')[1:-1]]
                table_rows.append(row_cells)
            continue
        else:
            if in_table:
                # Escribir la tabla acumulada
                if table_headers and table_rows:
                    add_styled_table(doc, table_headers, table_rows)
                in_table = False
                table_headers = []
                table_rows = []
        
        if not line_strip:
            continue
            
        # 2. Encabezados (Headers)
        if line_strip.startswith('# '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(18)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(line_strip[2:])
            run.font.name = 'Arial'
            run.font.size = Pt(16)
            run.font.bold = True
            run.font.color.rgb = NAVY_COLOR
            p.paragraph_format.keep_with_next = True
            
        elif line_strip.startswith('## '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(line_strip[3:])
            run.font.name = 'Arial'
            run.font.size = Pt(13)
            run.font.bold = True
            run.font.color.rgb = SLATE_COLOR
            p.paragraph_format.keep_with_next = True
            
        elif line_strip.startswith('### '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(line_strip[4:])
            run.font.name = 'Arial'
            run.font.size = Pt(11.5)
            run.font.bold = True
            run.font.color.rgb = SLATE_COLOR
            
        # 3. Listas
        elif line_strip.startswith('- ') or line_strip.startswith('* '):
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            parse_inline_formatting(p, line_strip[2:])
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(10.5)
                run.font.color.rgb = TEXT_COLOR
                
        # 4. Listas Numeradas (ej: 1. )
        elif re.match(r'^\d+\.\s', line_strip):
            match = re.match(r'^(\d+)\.\s(.*)', line_strip)
            num = match.group(1)
            content = match.group(2)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            p.add_run(f"{num}. ").bold = True
            parse_inline_formatting(p, content)
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(10.5)
                run.font.color.rgb = TEXT_COLOR

        # 5. Párrafo Normal
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.15
            parse_inline_formatting(p, line_strip)
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(10.5)
                run.font.color.rgb = TEXT_COLOR

    # Si el texto termina justo dentro de una tabla
    if in_table and table_headers and table_rows:
        add_styled_table(doc, table_headers, table_rows)

def build_docx(sections: Dict[str, str], filepath: str, query: str):
    """
    Compila todas las secciones generadas en un único archivo .docx estilizado.
    """
    doc = Document()
    
    # Configurar Márgenes (1 pulgada en todos los lados)
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        
        # Configurar Encabezado y Pie de página básicos
        header = section.header
        hp = header.paragraphs[0]
        hp.text = f"Reporte Clínico Quirúrgico: {query.upper()}"
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hp.runs[0].font.size = Pt(8.5)
        hp.runs[0].font.italic = True
        hp.runs[0].font.color.rgb = SLATE_COLOR
        
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.text = "Generado por Sistema Quirúrgico Pediátrico Multi-Agente"
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp.runs[0].font.size = Pt(8)
        fp.runs[0].font.color.rgb = SLATE_COLOR

    # 1. Página de Portada Quirúrgica Premium
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(100)
    title_p.paragraph_format.space_after = Pt(12)
    title_run = title_p.add_run("APUNTE CLÍNICO DE CIRUGÍA INFANTIL")
    title_run.font.name = 'Arial'
    title_run.font.size = Pt(24)
    title_run.font.bold = True
    title_run.font.color.rgb = NAVY_COLOR
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle_p = doc.add_paragraph()
    subtitle_p.paragraph_format.space_after = Pt(36)
    sub_run = subtitle_p.add_run(f"Tema: {query.upper()}\nSíntesis Multicéntrica de Evidencia con Consenso Multi-Agente")
    sub_run.font.name = 'Arial'
    sub_run.font.size = Pt(14)
    sub_run.font.color.rgb = SLATE_COLOR
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta_p = doc.add_paragraph()
    meta_p.paragraph_format.space_before = Pt(150)
    meta_run = meta_p.add_run("Consorcio Virtual de Agentes Expertos en Cirugía Pediátrica\nEvidencia: Oxford CEBM & Grado GRADE\nFormato: Word Document (.docx)")
    meta_run.font.size = Pt(10)
    meta_run.font.italic = True
    meta_run.font.color.rgb = SLATE_COLOR
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Salto de página para iniciar el contenido
    doc.add_page_break()

    # 2. Escribir las secciones modulares parseando su Markdown
    order = ["intro_embryo", "clinical_diag", "treatment_comp", "evidence_references"]
    
    for section_key in order:
        text = sections.get(section_key, "")
        if text:
            parse_markdown_to_docx(doc, text)
            # Agregar salto de página entre bloques principales para orden
            if section_key != order[-1]:
                doc.add_page_break()

    # Crear el directorio si no existe y guardar el archivo
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc.save(filepath)
    logger.info(f"Documento de Word guardado con éxito en: {filepath}")
