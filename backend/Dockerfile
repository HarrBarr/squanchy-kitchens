FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
WORKDIR /app

# Dependencies first for layer caching. The dev extra (pytest, httpx, ruff, mypy) is always
# installed so `docker compose run --rm api pytest` works with nothing but Docker on the host.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && uv pip install --system ".[dev]"

COPY . .
# --reinstall: the dependency layer above installed a stub `app` package (same name and
# version), and without it uv only "audits" and keeps the stub. Then the `alembic` command
# imported the empty stub and a clean (no-cache) build failed with "No module named
# 'app.config'".
RUN uv pip install --system --no-deps --reinstall . \
    && chmod +x entrypoint.sh \
    && mkdir -p /data/uploads /data/state

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
