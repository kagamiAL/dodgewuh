FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY simulation ./simulation
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
