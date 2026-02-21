# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .


# Stage 2: Runtime
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Conduit LLM Gateway"
LABEL org.opencontainers.image.description="Self-hosted LLM gateway and proxy"
LABEL org.opencontainers.image.source="https://github.com/conduit-llm/conduit"

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r conduit && useradd -r -g conduit conduit

COPY --from=builder /install /usr/local
COPY src/ /app/src/
COPY config/conduit.example.yaml /app/config/conduit.yaml
COPY config/pricing/ /app/config/pricing/
COPY alembic.ini /app/

WORKDIR /app
USER conduit

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    CONDUIT_ENV=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/admin/v1/health/live || exit 1

ENTRYPOINT ["python", "-m", "uvicorn", "conduit.app:create_app", "--factory"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--workers", "4"]