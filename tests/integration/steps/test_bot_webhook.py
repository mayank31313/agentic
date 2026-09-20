# tests/behaviour/steps/test_bot_webhook.py
import asyncio
import json

import httpx
import yaml
from pytest_bdd import given, scenarios, then, when, parsers
import logging

from agentic.app.gateway.adapters import OutboundMessage
from tests.integration.conftest import Scenario, get_user_agent

logger = logging.getLogger(__name__)
scenarios("../features/bot_webhook.feature")


@given("the docker compose stack is running", target_fixture="stack_ctx")
def stack_is_running(compose_stack, bot_base_url):
    return {"base_url": f"http://{bot_base_url}",
            "websocket_endpoint": f"ws://{bot_base_url}/ws"}


@when("I query the bot's health endpoint", target_fixture="response")
def query_health(stack_ctx, mcp_mock_server):
    logger.info(asyncio.run(mcp_mock_server.get_server_info()))
    return httpx.get(f"{stack_ctx['base_url']}/health", timeout=5)

@then(parsers.parse("the response status is {status:d}"))
def assert_status(response, status):
    assert response.status_code == status, response.text

def send_message(text: str, websocket):
    websocket.send(text)
    messages = []
    while True:
        response = websocket.recv()
        outbound_message = OutboundMessage.model_validate(json.loads(response))
        logger.info(f"Outbound Message: {outbound_message}")
        messages.append(outbound_message)
        if "Calling tool:" in outbound_message.text:
            continue

        return outbound_message, messages

@then(parsers.parse("Execute agent {scenario_file}"))
def execute_agent(websocket, judge, scenario_file):
    with open(f"tests/integration/scenarios/{scenario_file}", "r") as f:
        scenarios = yaml.load(f, Loader=yaml.FullLoader).get("scenarios")

    for scenario_dict in scenarios:
        scenario = Scenario(**scenario_dict)
        user_agent = get_user_agent(scenario.user_agent_prompt)
        message, messages = send_message(text=scenario.input_message, websocket=websocket)
        count = 0
        while count < 10:
            logger.info(f"Message from bot: {message}")
            user_response = user_agent.invoke(dict(query=message.metadata['response'][0]['text']))
            logger.info(f"User response: {user_response}")
            message, messages = send_message(text=user_response.content, websocket=websocket)
            judge_response = judge.invoke(
                dict(user_query="", response=message.metadata['response'][0]['text'], criterias=scenario.judge.criteria))

            logger.info(f"Judge verdict: {judge_response}")
            if judge_response.passed and judge_response.score >= 4:
                count = 12
                break
            else:
                logger.info(f"Judge failed: {judge_response.reasoning}")

            count += 1

        assert judge_response.passed and judge_response.score >= 4, f"Judge failed: {judge_response.reasoning}"
        if count == 12:
            logger.info("Agent Bootstrap is complete and there are no questions from bot")
