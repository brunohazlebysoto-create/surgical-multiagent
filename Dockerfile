FROM python:3.10-slim

WORKDIR /code

# Instalar dependencias del sistema adicionales (si fueran necesarias, pypdf/docx/pptx son puro python)
# RUN apt-get update && apt-get install -y ...

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . .

# Crear directorios de descargas y subidas con permisos adecuados
RUN mkdir -p /code/static/downloads /code/static/uploads /code/templates

# Hugging Face Spaces requiere exponer el puerto 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
