FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2-binary and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download CLIP model weights into the image layer
# (avoids first-startup download timeout in production)
# Override TRANSFORMERS_CACHE if a volume is preferred.
ARG PRELOAD_CLIP=false
RUN if [ "$PRELOAD_CLIP" = "true" ]; then \
      python -c "from transformers import CLIPModel, CLIPProcessor; \
                 CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32'); \
                 CLIPModel.from_pretrained('openai/clip-vit-base-patch32')"; \
    fi

COPY . .

CMD ["celery", "-A", "app.celery_app", "worker", "-l", "info", "-P", "prefork"]
