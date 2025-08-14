# ====== BUILD STAGE ======
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# Базовые зависимости для сборки (gcc и libpq-dev — на случай asyncpg/Postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Только манифесты — чтобы кэш устанавливаемых пакетов не сбивался
COPY pyproject.toml poetry.lock* ./

RUN poetry install --no-root --no-interaction --no-ansi

# ====== RUNTIME STAGE ======
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Скопировать установленные пакеты из builder
COPY --from=builder /usr/local /usr/local

# Скопировать исходники
COPY . .

# Нерутовый пользователь
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# (Опционально) healthcheck, если есть endpoint пинга
# HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import sys;sys.exit(0)"

# Запуск приложения
CMD ["python", "app.py"]
