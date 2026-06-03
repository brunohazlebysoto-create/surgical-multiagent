import os
import logging
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

logger = logging.getLogger("multiagent_pptx")

# Paleta de Colores
BG_COLOR = RGBColor(9, 13, 22)         # #090D16 (Azul oscuro profundo)
CARD_BG_COLOR = RGBColor(19, 26, 38)   # #131A26 (Azul de tarjeta)
TEAL_COLOR = RGBColor(0, 210, 196)     # #00D2C4 (Cian quirúrgico)
WHITE_COLOR = RGBColor(255, 255, 255)  # Blanco
GRAY_COLOR = RGBColor(200, 210, 220)   # Gris claro para texto secundario

def apply_dark_background(slide):
    """Establece un color de fondo azul oscuro sólido en la diapositiva."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = BG_COLOR

def add_slide_title(slide, text: str):
    """Agrega un título estándar a las diapositivas de contenido."""
    title_box = slide.shapes.add_textbox(Inches(0.75), Inches(0.5), Inches(11.833), Inches(0.8))
    tf = title_box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = 'Arial'
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = TEAL_COLOR
    p.alignment = PP_ALIGN.LEFT

def add_slide_references(slide, text: str):
    """Agrega una nota en el borde inferior indicando los papers/referencias utilizados."""
    if not text:
        return
    # Las dimensiones de la diapositiva son 13.333 x 7.5 pulgadas.
    ref_box = slide.shapes.add_textbox(Inches(0.75), Inches(6.8), Inches(11.833), Inches(0.4))
    tf = ref_box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    
    p = tf.paragraphs[0]
    p.text = f"Evidencia / Referencias: {text}"
    p.font.name = 'Arial'
    p.font.size = Pt(11)
    p.font.italic = True
    p.font.color.rgb = GRAY_COLOR
    p.alignment = PP_ALIGN.LEFT

def build_pptx(slides_list: list, filepath: str):
    """
    Toma la lista de diccionarios de diapositivas y genera una presentación PPTX
    16:9 premium y libre de errores de maquetación.
    """
    prs = Presentation()
    
    # 1. Configurar pantalla panorámica (Widescreen 16:9)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    # Usar un diseño de slide en blanco (índice 6 en plantillas por defecto)
    blank_layout = prs.slide_layouts[6]
    
    for i, s in enumerate(slides_list):
        slide = prs.slides.add_slide(blank_layout)
        apply_dark_background(slide)
        
        layout_type = s.get("layout", "bullet_points")
        
        # --- LAYOUT: TITLE ---
        if layout_type == "title":
            title_box = slide.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.333), Inches(3.0))
            tf = title_box.text_frame
            tf.word_wrap = True
            tf.alignment = PP_ALIGN.CENTER
            
            p1 = tf.paragraphs[0]
            p1.text = s.get("title", "Cirugía Pediátrica").upper()
            p1.font.name = 'Arial'
            p1.font.size = Pt(44)
            p1.font.bold = True
            p1.font.color.rgb = TEAL_COLOR
            p1.alignment = PP_ALIGN.CENTER
            
            p2 = tf.add_paragraph()
            p2.text = s.get("subtitle", "Análisis de Evidencia")
            p2.font.name = 'Arial'
            p2.font.size = Pt(20)
            p2.font.color.rgb = WHITE_COLOR
            p2.alignment = PP_ALIGN.CENTER
            
        # --- LAYOUT: BULLET POINTS ---
        elif layout_type == "bullet_points":
            title = s.get("title", "Título de Diapositiva")
            add_slide_title(slide, title)
            
            bullets = s.get("bullets", [])
            
            # Crear caja de texto para viñetas
            bullets_box = slide.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(11.333), Inches(4.8))
            tf = bullets_box.text_frame
            tf.word_wrap = True
            tf.margin_top = tf.margin_left = tf.margin_right = tf.margin_bottom = 0
            
            for idx, bullet_text in enumerate(bullets[:5]):
                p = tf.add_paragraph() if idx > 0 else tf.paragraphs[0]
                p.text = f"•  {bullet_text}"
                p.font.name = 'Arial'
                p.font.size = Pt(18)
                p.font.color.rgb = WHITE_COLOR
                # Espaciado entre viñetas
                p.space_after = Pt(14)
                
        # --- LAYOUT: COMPARISON TABLE ---
        elif layout_type == "comparison_table":
            title = s.get("title", "Tabla Comparativa")
            add_slide_title(slide, title)
            
            headers = s.get("headers", [])
            rows = s.get("rows", [])
            
            if not headers:
                continue
                
            num_cols = len(headers)
            num_rows = len(rows) + 1
            
            left = Inches(1.0)
            top = Inches(1.8)
            width = Inches(11.333)
            height = Inches(4.5)
            
            table_shape = slide.shapes.add_table(num_rows, num_cols, left, top, width, height)
            table = table_shape.table
            
            # Formatear Cabecera de Tabla
            for col_idx, header in enumerate(headers):
                cell = table.cell(0, col_idx)
                cell.text = header
                cell.fill.solid()
                cell.fill.fore_color.rgb = CARD_BG_COLOR
                
                p = cell.text_frame.paragraphs[0]
                p.alignment = PP_ALIGN.CENTER
                p.font.name = 'Arial'
                p.font.size = Pt(16)
                p.font.bold = True
                p.font.color.rgb = TEAL_COLOR
                
            # Formatear Filas de Datos
            for row_idx, row_data in enumerate(rows):
                for col_idx, cell_value in enumerate(row_data):
                    if col_idx >= num_cols:
                        continue
                    cell = table.cell(row_idx + 1, col_idx)
                    cell.text = cell_value
                    
                    p = cell.text_frame.paragraphs[0]
                    p.alignment = PP_ALIGN.LEFT
                    p.font.name = 'Arial'
                    p.font.size = Pt(14)
                    p.font.color.rgb = WHITE_COLOR
                    
        # --- LAYOUT: STEP PROCESS (Horizontal Cards) ---
        elif layout_type == "step_process":
            title = s.get("title", "Proceso Quirúrgico Paso a Paso")
            add_slide_title(slide, title)
            
            steps = s.get("steps", [])
            num_steps = min(len(steps), 4) # Max 4 pasos horizontales
            
            if not steps:
                continue
                
            # Calcular ancho de cada tarjeta
            total_width = Inches(11.333)
            gap = Inches(0.4)
            card_width = (total_width - (gap * (num_steps - 1))) / num_steps
            card_height = Inches(4.2)
            card_top = Inches(2.0)
            
            for idx in range(num_steps):
                card_left = Inches(1.0) + idx * (card_width + gap)
                
                # Crear tarjeta de fondo
                shape = slide.shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE, card_left, card_top, card_width, card_height
                )
                shape.fill.solid()
                shape.fill.fore_color.rgb = CARD_BG_COLOR
                shape.line.color.rgb = TEAL_COLOR
                shape.line.width = Pt(1.5)
                
                # Caja de texto interna para la descripción del paso
                tf = shape.text_frame
                tf.word_wrap = True
                tf.margin_top = Inches(0.3)
                tf.margin_left = tf.margin_right = Inches(0.2)
                
                # Número de paso
                p_num = tf.paragraphs[0]
                p_num.text = f"PASO {idx + 1}"
                p_num.font.name = 'Arial'
                p_num.font.size = Pt(20)
                p_num.font.bold = True
                p_num.font.color.rgb = TEAL_COLOR
                p_num.alignment = PP_ALIGN.CENTER
                p_num.space_after = Pt(14)
                
                # Descripción del paso
                p_desc = tf.add_paragraph()
                p_desc.text = steps[idx]
                p_desc.font.name = 'Arial'
                p_desc.font.size = Pt(14)
                p_desc.font.color.rgb = WHITE_COLOR
                p_desc.alignment = PP_ALIGN.LEFT
                
        # --- LAYOUT: METRICS (Gran Cifra/Recomendación) ---
        elif layout_type == "metrics":
            title = s.get("title", "Medida Destacada")
            add_slide_title(slide, title)
            
            metric_val = s.get("metric_value", "99%")
            metric_lbl = s.get("metric_label", "Descripción")
            
            # 1. Caja del Número Gigante
            val_box = slide.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(11.333), Inches(2.2))
            tf_val = val_box.text_frame
            tf_val.word_wrap = True
            p_val = tf_val.paragraphs[0]
            p_val.text = metric_val
            p_val.font.name = 'Arial'
            p_val.font.size = Pt(80)
            p_val.font.bold = True
            p_val.font.color.rgb = TEAL_COLOR
            p_val.alignment = PP_ALIGN.CENTER
            
            # 2. Caja de la etiqueta explicativa
            lbl_box = slide.shapes.add_textbox(Inches(1.5), Inches(4.5), Inches(10.333), Inches(1.8))
            tf_lbl = lbl_box.text_frame
            tf_lbl.word_wrap = True
            p_lbl = tf_lbl.paragraphs[0]
            p_lbl.text = metric_lbl
            p_lbl.font.name = 'Arial'
            p_lbl.font.size = Pt(22)
            p_lbl.font.color.rgb = WHITE_COLOR
            p_lbl.alignment = PP_ALIGN.CENTER

        # Agregar notas de referencias al borde inferior si existen
        references = s.get("references", "")
        if references:
            add_slide_references(slide, references)

    # Crear directorio si no existe y guardar
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    prs.save(filepath)
    logger.info(f"Presentación de PowerPoint guardada con éxito en: {filepath}")
