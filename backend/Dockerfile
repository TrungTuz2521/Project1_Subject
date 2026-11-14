# Backend image: the same Python as local development and tests.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 app
USER app

# The platform sets PORT; gunicorn serves the API. The scheduler runs as a separate process (fly.toml / Procfile)
# or, on Render free, inside the web process (RUN_SCHEDULER_IN_WEB=true with WEB_CONCURRENCY=1, see render.yaml).
EXPOSE 8080
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8080} --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-1} --timeout 60"]
