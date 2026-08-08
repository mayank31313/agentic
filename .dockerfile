FROM python:3.13-slim
RUN apt update && apt install ffmpeg -y
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /bot
COPY pyproject.toml README.md /bot/
RUN uv sync --no-install-project
COPY src /bot/src
ENV PATH="/root/.local/bin:$PATH"
RUN uv sync && uv tool install .

CMD ["agentic", "run"]