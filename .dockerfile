FROM python:3.14-slim
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /bin/

ENV AGENTIC_BOT_HOME=/bot
WORKDIR $AGENTIC_BOT_HOME
COPY pyproject.toml uv.lock README.md LICENSE CONTRIBUTING.md $AGENTIC_BOT_HOME/
RUN uv sync --no-install-project
COPY . $AGENTIC_BOT_HOME/
ENV PATH="/root/.local/bin:$PATH"

RUN uv sync && uv run alembic upgrade head

CMD ["uv", "run","agentic", "run"]