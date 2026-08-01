# conftest.py

import os

import pytest
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents import get_main_agent
from app.scheduler.tools import get_cron_tools

CRON_SCHEDULE_FILENAME = "tests/resources/cron_schedules.json"


class JudgeVerdict(BaseModel):
    passed: bool = Field(description="Whether the response meets the criteria")
    reasoning: str = Field(description="Brief explanation for the verdict")
    score: int = Field(description="Score from 1-5", ge=1, le=5)

@pytest.fixture(autouse=True)
def reset():
    """Runs before every test — resets fake state so tests don't leak into each other."""
    if os.path.exists(CRON_SCHEDULE_FILENAME):
        os.remove(CRON_SCHEDULE_FILENAME)
    yield

@pytest.fixture
def judge():
    os.environ['OPENAI_API_BASE'] = 'https://integrate.api.nvidia.com/v1'
    os.environ['OPENAI_API_KEY'] = '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'

    judge_prompt = """You are a judge that evaluates the quality of response from an AI agent.
You will be given a user query, response and a set of criteria. Your task is to determine whether the response meets the criteria, and provide a brief reasoning for your verdict. You will also assign a score from 1 to 5, where 1 is the lowest and 5 is the highest.

User: {user_query}
Response: {response}
Criterias:
{criterias}
    """
    return ChatPromptTemplate.from_template(judge_prompt) | ChatOpenAI(model="nvidia/nemotron-3-super-120b-a12b", temperature=0).with_structured_output(JudgeVerdict)

@pytest.fixture
def tools():
    return get_cron_tools()

@pytest.fixture
def agent(tools):
    # Pin the model version explicitly — don't float on "latest"
    return get_main_agent(tools)