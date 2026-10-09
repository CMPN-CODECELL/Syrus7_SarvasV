FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS runtime
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
