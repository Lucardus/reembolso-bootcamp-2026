FROM python:3.11-slim

# poppler e tesseract: o anexo pode ser foto de recibo.
# gcc e python3-dev: o PyStemmer, que vem com o retriever BM25 do LlamaIndex,
# não tem wheel pronto e compila na instalação. Sem eles o build quebra.
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils tesseract-ocr tesseract-ocr-por \
        gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# O índice entra pronto. Não construa índice no build nem no start.
COPY ingest/ ./ingest/
COPY kb/ ./kb/
COPY app/ ./app/
COPY storage/ ./storage/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
