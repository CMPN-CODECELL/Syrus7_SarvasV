FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY frontend ./frontend
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
