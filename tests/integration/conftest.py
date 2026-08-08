# conftest.py
import os

import pytest
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

CRON_SCHEDULE_FILENAME = "tests/resources/cron_schedules.json"
AGENTIC_CONFIG_FILENAME = "tests/resources/agentic.json"


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
