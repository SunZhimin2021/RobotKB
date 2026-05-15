# bge-reranker-v2-m3 reranker service — ARM64 + CUDA (Jetson)
FROM nvcr.io/nvidia/l4t-ml:r36.2.0-py3

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    fastapi>=0.110 \
    uvicorn[standard]>=0.29 \
    pydantic>=2.0 \
    pydantic-settings>=2.0 \
    python-json-logger>=3.0 \
    onnxruntime-gpu>=1.18 \
    tokenizers>=0.19 \
    numpy>=1.24

COPY src/common           /app/src/common
COPY src/embedding_service /app/src/embedding_service
# reranker imports _gpu_semaphore from embedding_service.model
COPY src/reranker_service /app/src/reranker_service

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8002

CMD ["python", "-m", "reranker_service.main"]
