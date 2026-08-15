FROM python:3.14-slim
RUN apt update && apt install ffmpeg -y
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /bot
COPY pyproject.toml uv.lock README.md LICENSE CONTRIBUTING.md /bot/
RUN uv sync --no-install-project
COPY src /bot/src
ENV PATH="/root/.local/bin:$PATH"
RUN uv sync && uv tool install .

CMD ["agentic", "run"]