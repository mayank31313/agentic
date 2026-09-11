# conftest.py
import json
import logging
import os
import shutil
import subprocess

import pytest
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from mcptest import load_fixture
from mcptest.conformance import InProcessServer
from mcptest.mock_server import MockMCPServer
from pydantic import BaseModel, Field
from testcontainers.compose import DockerCompose
from websockets.sync.client import connect

from agentic import AgenticConfig
from agentic.app.config import ModelConfig, AgentConfig

CRON_SCHEDULE_FILENAME = "tests/resources/cron_schedules.json"
AGENTIC_CONFIG_FILENAME = "tests/resources/agentic.json"
MCP_FIXTURE_PATH = "tests/integration/mcp_fixtures/main.yaml"

AGENTIC_CONFIG_JSON = "tests/resources/agentic_test.json"
AGENTIC_WORKSPACE_PATH = "tests/workspace"
BOOTSTRAP_CONFIG_PATH = "tests/resources/BOOTSTRAP.md"

logger = logging.getLogger(__name__)

class JudgeVerdict(BaseModel):
    passed: bool = Field(description="Whether the response meets the criteria")
    reasoning: str = Field(description="Brief explanation for the verdict")
    score: int = Field(description="Score from 1-5", ge=1, le=5)

requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not available"
)
def bootstrap_main_agent():
    """Bootstrap the agentic workspace with a default agent."""
    if os.path.exists(AGENTIC_WORKSPACE_PATH):
        shutil.rmtree(AGENTIC_WORKSPACE_PATH)
    os.makedirs(AGENTIC_WORKSPACE_PATH, exist_ok=True)
    agent_instructions_path = os.path.join(AGENTIC_WORKSPACE_PATH, "agents", "main")
    os.makedirs(agent_instructions_path, exist_ok=True)
    shutil.copyfile(BOOTSTRAP_CONFIG_PATH, os.path.join(AGENTIC_WORKSPACE_PATH, "BOOTSTRAP.md"))

    instructions = "# Main Agent Instructions\n\nRead and Execute the instructions from BOOTSTRAP.md file in the root of the workspace."
    with open(BOOTSTRAP_CONFIG_PATH, "r") as bootstrap_stream:
        instructions = bootstrap_stream.read()

    with open(os.path.join(agent_instructions_path, "instructions.md"), "w") as f:
        agent_config = AgentConfig.model_validate({
              "workspace_dir": "./workspace",
              "name": "main",
              "description": "Main Agent for system",
              "model_id": "custom-nemotron-3-super-120b-a12b",
              "tools": [],
              "denied_tools": [
                "mcp-activate-profile",
                "mcp-add",
                "mcp-config-set",
                "mcp-create-profile",
                "mcp-exec",
                "mcp-find",
                "mcp-remove",
                "execute_code"
              ],
              "skills": [
                {
                  "path": "./src/skills/",
                  "virtual_path": "/skills/"
                }
              ]
            }).model_dump_json(indent=4, exclude={'agent_model_config', 'instructions'})
        f.write(f"{agent_config}\n---\n{instructions}\n")

@pytest.fixture(scope="session")
def compose_stack():
    bootstrap_main_agent()
    with open(AGENTIC_CONFIG_JSON, "w") as config_file:
        agentic_config = AgenticConfig(
            workspace="./workspace",
            models=[
              ModelConfig.model_validate({
                    "model": "openai:nvidia/nemotron-3-super-120b-a12b",
                    "model_id": "custom-nemotron-3-super-120b-a12b",
                    "context_window": 128000,
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "api_key": {
                        "env_key": "NVIDIA_API_KEY"
                    }
              }),
                # ModelConfig.model_validate({
                # "model": "openai:gemma-4-e2b-it",
                # "model_id": "custom-gemma-4-e2b-it",
                # "context_window": 256000,
                # "base_url": "http://host.docker.internal:8080/v1",
                # "api_key": {
                #     "env_key": "NVIDIA_API_KEY"
                # }
            # })
            ],
            mcpServers={
                "agentic_mcp": {
                    "url": "http://mcp:8811/mcp",
                    "transport": "http"
                }
            },
        )

        config_json = agentic_config.model_dump(mode='json')
        json.dump(config_json, config_file, indent=4)

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
    # stack.stop(down=False)

@pytest.fixture(scope="session")
def websocket(bot_base_url):
    with connect(f"ws://{bot_base_url}/ws/test_user") as websocket:
        yield websocket

@pytest.fixture(scope="session")
def bot_base_url(compose_stack):
    host, port = compose_stack.get_service_host_and_port(service_name="bot", port=5000)
    return f"{host}:{port}"

@pytest.fixture(scope="session")
def mcp_mock_server():
    fixtures = load_fixture(MCP_FIXTURE_PATH)
    mock_server = MockMCPServer(fixtures)
    server = InProcessServer(mock_server, fixtures)

    yield server
    server.close()

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
def user_agent():
    load_dotenv()
    user_agent_prompt = """You are test user, and you are testing the bot's ability to respond to messages. Only output the response text, do not include any other text or formatting. You will be given query or questions from the bot, and your task is to respond to them in a casual and friendly manner. 
    You should not provide any additional information or context beyond what is asked in the query. Your responses should be concise and to the point. If question is one of below answers, you should respond with the corresponding answer. If the question is not one of the below answers, you should respond with a sensible response relating to below test question and answers in context.
    
    Bot Name: Agentic
    User Name: Emmett
    Bot task: Bot is a personal assistant for emmett and it assists emmett with various daily tasks and provide information as needed, schedule appointments, reminders, infrastructure management
    About User: Emmett is a software engineer and he is working on a project that involves building a personal assistant bot. He is looking for a bot that can help him with various tasks and provide information as needed. He is also looking for a bot that can help him with scheduling appointments, reminders, and infrastructure management.
    
    Bot Query: {query}
    """

    model = init_chat_model(
        model="openai:nvidia/nemotron-3-super-120b-a12b",
        base_url=f"https://integrate.api.nvidia.com/v1",
        api_key=os.environ['NVIDIA_API_KEY']
    )

    return ChatPromptTemplate.from_template(user_agent_prompt) | model

@pytest.fixture(scope="session")
def judge():
    load_dotenv()
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
        api_key=os.environ['NVIDIA_API_KEY']
    )

    return ChatPromptTemplate.from_template(judge_prompt) | model.with_structured_output(JudgeVerdict)
