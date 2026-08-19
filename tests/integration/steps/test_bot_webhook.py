# tests/behaviour/steps/test_bot_webhook.py
import json

import httpx
from pytest_bdd import given, scenarios, then, when, parsers
import logging

from agentic.app.gateway.adapters import OutboundMessage
from agentic.app.gateway.adapters.websockets import WebSocketsAdapter

logger = logging.getLogger(__name__)
scenarios("../features/bot_webhook.feature")


@given("the docker compose stack is running", target_fixture="stack_ctx")
def stack_is_running(compose_stack, bot_base_url):
    return {"base_url": f"http://{bot_base_url}",
            "websocket_endpoint": f"ws://{bot_base_url}/ws"}


@when("I query the bot's health endpoint", target_fixture="response")
def query_health(stack_ctx):
    return httpx.get(f"{stack_ctx['base_url']}/health", timeout=5)

@then(parsers.parse("the response status is {status:d}"))
def assert_status(response, status):
    assert response.status_code == status, response.text

def send_message(text: str, websocket):
    websocket.send(text)
    while True:
        response = websocket.recv()
        outbound_message = OutboundMessage.model_validate(json.loads(response))
        logger.info(f"Outbound Message: {outbound_message}")
        if "Calling tool:" in outbound_message.text:
            continue

        return outbound_message



@then("connect to bot using websocket and say hey")
def connect_to_bot(websocket, judge):
    text =  "Hey"
    message = send_message(text = text, websocket=websocket)

    assert message.channel == WebSocketsAdapter.name, f"Expected channel {WebSocketsAdapter.name}, got {message.channel}"
    assert message.chat_id == "test_user", f"Expected chat_id 'test_user', got {message.chat_id}"

    response_text = message.metadata['response'][0]['text']
    assert response_text, "Expected non-empty response text"
    judge_response  = judge.invoke(dict(user_query=text, response=response_text, criterias="Response is a casual greeting"), timeout=10)

    logger.info(f"Judge verdict: {judge_response}")
    assert judge_response.passed and judge_response.score >= 4, f"Judge failed: {judge_response.reasoning}"

@then(parsers.parse("Send message to bot \"{message}\" and expect \"{criteria}\""))
def send_message_expect(message, criteria, websocket):
    message = send_message(text = message, websocket=websocket)
    logger.info(f"Response: {message}")
