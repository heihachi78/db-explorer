FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DATA_DIR=/data
WORKDIR /app
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
RUN pip install --no-cache-dir /app/backend
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000} --workers 1"]
