FROM ghcr.io/astral-sh/uv:0.6.17-python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    WEB_HOST=0.0.0.0

RUN apt-get update \
    && apt-get install --no-install-recommends -y fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE NOTICE.md ./
COPY LICENSES ./LICENSES
COPY src ./src
RUN uv sync --locked --no-dev

RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home appuser \
    && mkdir -p /var/lib/form /var/lib/form-bot \
    && chown -R appuser:appuser /app /var/lib/form /var/lib/form-bot
USER appuser

EXPOSE 3001
CMD ["uv", "run", "--no-sync", "garmin-reptrace"]
