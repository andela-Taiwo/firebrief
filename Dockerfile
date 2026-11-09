# Base image pinned by digest. uv also provides Python 3.12, so the runtime
# stage uses the same pinned image rather than a second, drifting base.
FROM ghcr.io/astral-sh/uv:0.9.5-python3.12-bookworm-slim@sha256:f4a1d5fb780441a485a8e3f88b30344ab858ed8acde3cc35f1ef59516b253ec8 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first: this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev

FROM ghcr.io/astral-sh/uv:0.9.5-python3.12-bookworm-slim@sha256:f4a1d5fb780441a485a8e3f88b30344ab858ed8acde3cc35f1ef59516b253ec8 AS runtime

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/config /app/config

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

# Smoke test until the API exists (F18): importing the package must work.
CMD ["python", "-c", "import firebrief; print('firebrief', firebrief.__version__)"]
