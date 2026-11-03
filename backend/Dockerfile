# The operating system layer, shared by every stage. It comes before any Python dependency so
# that changing a dependency does not download and install Tesseract again.
FROM python:3.12-slim AS base
# Tesseract is the OCR engine; the English language data comes with the package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Runtime dependencies only: copied into the final image.
FROM base AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
# The cache mount keeps uv's downloaded wheels between builds, so after a dependency change only
# the new or changed packages are downloaded (the big ones, such as OpenCV, are not fetched again).
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Runtime plus dev dependencies and the tests. It does not build on `build`, so building the
# test image never installs the runtime-only environment as well.
FROM base AS test
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY prompts ./prompts
COPY tests ./tests
ENV PATH="/app/.venv/bin:$PATH"
CMD ["pytest"]

FROM base
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY prompts ./prompts
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
