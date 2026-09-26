FROM python:3.12-slim

ENV TZ=America/Argentina/Buenos_Aires \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Sistema: compilación de psycopg2, psql (seed), zona horaria, curl (healthcheck)
# y librerías de WeasyPrint.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev postgresql-client tzdata curl \
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi-dev shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements antes que el código: cache de capas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
