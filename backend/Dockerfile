# --- Backend image: FastAPI gateway on Python 3.12 ---
FROM python:3.12-slim

# Keep Python lean and predictable in containers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer). psycopg[binary] bundles libpq, so no
# system packages are required beyond the slim base.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application (app package, alembic config/migrations, pytest config).
COPY . .

# Run migrations, then start the server. Executable entrypoint.
RUN chmod +x entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
