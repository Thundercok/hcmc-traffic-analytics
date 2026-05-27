FROM python:3.11-slim

WORKDIR /app

# System dependencies for PIL and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libjpeg62-turbo-dev \
    && rm -rf /var/lib/apt/lists/*

# Add user
RUN useradd -m -u 1000 user

# Install requirements
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy application files
COPY --chown=user:user ZIP /app/ZIP
COPY --chown=user:user backend /app/backend

# Switch to user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    TF_ZIP_MODEL_PATH=/app/ZIP/checkpoints/demo_data/best_mae_0_quantized.onnx \
    TF_HOST=0.0.0.0 \
    TF_PORT=8000 \
    WRITER_INTERVAL_SECONDS=300

EXPOSE 8000

# Run directly without uvicorn for simpler container
CMD ["python", "-m", "backend.main"]
