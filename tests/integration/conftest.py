# conftest.py
import logging
import os
import shutil
import subprocess

import pytest
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from testcontainers.compose import DockerCompose
from websockets.sync.client import connect

CRON_SCHEDULE_FILENAME = "tests/resources/cron_schedules.json"
AGENTIC_CONFIG_FILENAME = "tests/resources/agentic.json"

logger = logging.getLogger(__name__)

class JudgeVerdict(BaseModel):
    passed: bool = Field(description="Whether the response meets the criteria")
    reasoning: str = Field(description="Brief explanation for the verdict")
    score: int = Field(description="Score from 1-5", ge=1, le=5)

requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not available"
)

@pytest.fixture(scope="session")
def compose_stack():
    stack = DockerCompose(
        context=".",  # repo root, where docker-compose.yaml lives
        compose_file_name=["docker-compose.yaml", "docker-compose-tests.yaml"],
        pull=False,
        build=True,
        wait=True,  # blocks until healthchecks pass
        env_file=[".env"],
    )
    with stack:
        yield stack
    stack.stop(down=True)

@pytest.fixture(scope="session")
def websocket(bot_base_url):
    with connect(f"ws://{bot_base_url}/ws/test_user") as websocket:
        yield websocket

@pytest.fixture(scope="session")
def bot_base_url(compose_stack):
    host, port = compose_stack.get_service_host_and_port(service_name="bot", port=5000)
    return f"{host}:{port}"

def scale_service(stack: DockerCompose, service: str, replicas: int) -> None:
    """Scale a compose service up/down without recreating unrelated services."""
    cmd = [*stack.docker_compose_command(), "up", "-d", "--no-recreate", "--scale", f"{service}={replicas}"]
    subprocess.run(cmd, cwd=str(stack.context), check=True, capture_output=True)

@pytest.fixture(autouse=True)
def reset():
    """Runs before every test — resets fake state so tests don't leak into each other."""
    if os.path.exists(CRON_SCHEDULE_FILENAME):
        os.remove(CRON_SCHEDULE_FILENAME)
    yield

@pytest.fixture(scope="session")
def judge():
    judge_prompt = """You are a judge that evaluates the quality of response from an AI agent.
You will be given a user query, response and a set of criteria. Your task is to determine whether the response meets the criteria, and provide a brief reasoning for your verdict. You will also assign a score from 1 to 5, where 1 is the lowest and 5 is the highest.

User: {user_query}
Response: {response}
Criterias:
{criterias}
    """
    model = init_chat_model(
        model="openai:nvidia/nemotron-3-super-120b-a12b",
        base_url=f"https://integrate.api.nvidia.com/v1",
        api_key="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"
    )

    return ChatPromptTemplate.from_template(judge_prompt) | model.with_structured_output(JudgeVerdict)
