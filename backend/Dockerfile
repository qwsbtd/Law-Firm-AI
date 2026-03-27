FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    poppler-utils tesseract-ocr curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-extra.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-extra.txt

COPY . .

RUN mkdir -p /app/data/chroma /app/data/uploads /app/data/library

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
