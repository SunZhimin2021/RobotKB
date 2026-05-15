# bge-m3 embedding service — ARM64 + CUDA (Jetson)
# Base image: ONNX Runtime with CUDA support for Jetson (aarch64)
FROM nvcr.io/nvidia/l4t-ml:r36.2.0-py3

WORKDIR /app

# Install Python deps
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

# Copy source
COPY src/common          /app/src/common
COPY src/embedding_service /app/src/embedding_service

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["python", "-m", "embedding_service.main"]
