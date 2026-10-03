FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY resource_control ./resource_control
COPY templates ./templates
COPY static ./static
COPY wsgi.py .

RUN chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=8s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "30", "--graceful-timeout", "20", "--worker-tmp-dir", "/tmp", "--no-control-socket", "--access-logfile", "-", "wsgi:app"]
