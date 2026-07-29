FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg2 build are avoided by using the binary wheel.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Non-root runtime user (least privilege).
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000
# Shell form so ${PORT} expands: Render/Fly inject PORT; default to 8000 locally.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
