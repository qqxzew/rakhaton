# Cloud image: FastAPI backend + built frontend. Build context is the staging dir made by stage.sh.
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY config/ /app/config/
COPY iris/ /app/iris/
COPY --from=web /web/dist /app/frontend/dist
COPY data/ /app/data/
COPY entrypoint.sh boot.py /app/
RUN tr -d '\r' < /app/entrypoint.sh > /tmp/ep && mv /tmp/ep /app/entrypoint.sh && chmod +x /app/entrypoint.sh
ENV PATH="/app/backend/.venv/bin:$PATH" PYTHONPATH=/app/backend DATA_DIR=/app/data SERVE_FRONTEND=1 \
    SMTP_HOST=localhost PYTHONUNBUFFERED=1 VECTOR_MATCH=off HF_HUB_OFFLINE=1 ML_PREDICT=off IRIS_SQL_POOL=1
EXPOSE 8000
CMD ["/app/entrypoint.sh"]
