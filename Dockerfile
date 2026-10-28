FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY distocad ./distocad
RUN pip install --no-cache-dir .
COPY web ./web

RUN useradd --system --uid 10001 --no-create-home app && mkdir /data && chown app /data
USER app

ENV DISTO_EPHEMERAL_DIR=/data
WORKDIR /app/web

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=3)"
CMD ["gunicorn", "distoweb.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--max-requests", "500"]
