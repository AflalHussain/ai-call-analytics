# Backend — FastAPI + uvicorn, Python 3.11.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Runtime deps. Kept as an explicit list (mirrors pyproject.toml) so this layer
# caches independently of the app code below — asyncpg / pydantic-core / uvloop
# all ship manylinux wheels, so no compiler is needed on slim.
# Keep in sync with backend/pyproject.toml [project.dependencies].
RUN pip install --no-cache-dir \
      "fastapi>=0.115" \
      "uvicorn[standard]>=0.32" \
      "asyncpg>=0.30" \
      "pydantic>=2.9" \
      "httpx>=0.27"

COPY app ./app
COPY scripts ./scripts
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
