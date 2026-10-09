# Rodem MES Solution — 앱 이미지 (코어 + 팩 + 선택 모듈). 비밀값은 이미지에 넣지 않는다 — 실행 시 환경변수 또는 /data 볼륨.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev && chmod +x docker/entrypoint.sh \
 && useradd --system --home /app mes && mkdir -p /data && chown -R mes /app /data
USER mes

ENV PATH="/app/.venv/bin:$PATH" MES_ENV=prod MES_PORT=8030
EXPOSE 8030
ENTRYPOINT ["docker/entrypoint.sh"]
