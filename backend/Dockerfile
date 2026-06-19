FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# unixODBC runtime: data/synapse.py imports pyodbc at module load, so the lib is
# required even on the seed-data path. Actually connecting to Azure Synapse also
# needs the Microsoft ODBC Driver 18 (msodbcsql18) — add it only if you enable Synapse.
RUN apt-get update \
    && apt-get install -y --no-install-recommends unixodbc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 3000
CMD ["sh", "-c", "uv run --frozen --no-dev uvicorn main:app --host 0.0.0.0 --port ${PORT:-3000} --workers ${WEB_CONCURRENCY:-1}"]
