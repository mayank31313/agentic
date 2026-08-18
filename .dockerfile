FROM python:3.14-slim
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /bin/
WORKDIR /bot
COPY pyproject.toml uv.lock README.md LICENSE CONTRIBUTING.md /bot/
RUN uv sync --no-install-project
COPY src /bot/src
ENV PATH="/root/.local/bin:$PATH"
RUN uv sync

CMD ["uv", "run","agentic", "run"]