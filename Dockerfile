FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    LLM_MODEL=qwen2.5:3b

WORKDIR /app

# Install minimal OS dependencies for network health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application modules, corpus, and evaluation assets
COPY app/ app/
COPY corpus/ corpus/
COPY eval/ eval/
COPY scripts/ scripts/
COPY Makefile .

# Build index at image build time so container runs self-contained without pre-built index/ in context
RUN python -m app.ingest --rebuild

EXPOSE 8080

# Run API server
CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8080"]
