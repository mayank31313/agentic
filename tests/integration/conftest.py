# conftest.py
import os
import shutil
import subprocess

import pytest
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from testcontainers.compose import DockerCompose

CRON_SCHEDULE_FILENAME = "tests/resources/cron_schedules.json"
AGENTIC_CONFIG_FILENAME = "tests/resources/agentic.json"


class JudgeVerdict(BaseModel):
    passed: bool = Field(description="Whether the response meets the criteria")
    reasoning: str = Field(description="Brief explanation for the verdict")
    score: int = Field(description="Score from 1-5", ge=1, le=5)

requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not available"
)


@pytest.fixture(scope="module")
def compose_stack():
    stack = DockerCompose(
        context=".",  # repo root, where docker-compose.yaml lives
        compose_file_name=["docker-compose.yaml"],
        pull=False,
        build=False,
        wait=True,  # blocks until healthchecks pass
    )
    with stack:
        yield stack


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


def judge():
    judge_prompt = """You are a judge that evaluates the quality of response from an AI agent.
You will be given a user query, response and a set of criteria. Your task is to determine whether the response meets the criteria, and provide a brief reasoning for your verdict. You will also assign a score from 1 to 5, where 1 is the lowest and 5 is the highest.

User: {user_query}
Response: {response}
Criterias:
{criterias}
    """
    return ChatPromptTemplate.from_template(judge_prompt) | ChatOpenAI(
        model="nvidia/nemotron-3-super-120b-a12b", temperature=0
    ).with_structured_output(JudgeVerdict)
