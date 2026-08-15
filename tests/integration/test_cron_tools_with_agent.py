# import json
# import logging
# import os
# import unittest
#
# import tinydb
# from cndi.annotations import Bean, Component
# from cndi.env import RCN_ENVS_CONFIG
# from cndi.tests import cndi_context_test
#
# from agentic.app.config import AgentConfig, AgenticConfig
# from agentic.app.constants import TELEGRAM_BOT_DEFAULT_CHAT_ID
# from agentic.app.scheduler.tools import CronSchedule
# from tests.integration.conftest import judge
#
# logger = logging.getLogger(__name__)
#
# CRON_SCHEDULE_FILENAME = "tests/resources/cron_schedules.json"
# os.environ["CRON_SCHEDULE_FILENAME"] = CRON_SCHEDULE_FILENAME
# os.environ["TELEGRAM_CHAT_ID"] = "8705816265"
#
#
# @Component
# class TestAgents:
#     def __init__(self, agenticConfig: AgenticConfig):
#         print(f"Initializing TestAgents with agenticConfig: {agenticConfig}")
#         self.agent = get_main_agent(
#             agent_config=agenticConfig.agents[0],
#             tools=[],
#             tool_registry=ToolsRegistry(),
#         )
#         self.judge = judge()
#
#
# # @pytest.fixture
# # def tools(mocker):
# #     eventBus_mock = mocker.patch(EventBus.__module__ + '.' + EventBus.__name__)
# #
# #     return get_cron_tools(eventBus_mock)
#
#
# @Bean()
# def agenticConfig() -> AgenticConfig:
#     return AgenticConfig(
#         workspace="./workspace",
#         agents=[
#             AgentConfig(
#                 system_prompt_path="AGENTS.md",
#                 workspace_dir="./workspace",
#                 name="main",
#                 model="openai:nvidia/nemotron-3-super-120b-a12b",
#             )
#         ],
#         mcpServers=dict(),
#     )
#
#
# class TestCronToolsWithAgent(unittest.TestCase):
#     @cndi_context_test
#     def test_cron_create_tool(self, test_agent: TestAgents):
#         agent = test_agent.agent
#         os.environ[RCN_ENVS_CONFIG + "." + TELEGRAM_BOT_DEFAULT_CHAT_ID] = "8705816265"
#         user_query = "Create a cron job to run at 6 AM everyday to Research on latest news about technology and cyber on the internet and provide a detailed summary with key points, sources, and potential implications."
#         config = {"configurable": {"thread_id": "session-123"}}
#
#         result = agent.invoke(
#             {
#                 "messages": [("user", user_query)],
#             },
#             config=config,
#         )
#
#         final_messages = list(
#             filter(lambda x: x["type"] == "text", result["messages"][-1].content)
#         )
#         assert final_messages.__len__() == 1
#         logger.info(f"Final message: {final_messages[0]}")
#         judge_result = test_agent.judge.invoke(
#             {
#                 "user_query": user_query,
#                 "response": final_messages[0]["text"],
#                 "criterias": "The response should confirm that the cron job has been created successfully with correct schedule.",
#             }
#         )
#
#         assert judge_result.passed, f"Test failed: {judge_result.reasoning}"
#         assert judge_result.score >= 4, f"Test failed: {judge_result.score}"
#         logger.info(os.environ.get("CRON_SCHEDULE_FILENAME"))
#         assert os.path.exists(os.environ.get("CRON_SCHEDULE_FILENAME"))
#         with open(os.environ.get("CRON_SCHEDULE_FILENAME"), "r") as f:
#             data = json.load(f)["_default"]
#
#             logger.info(data)
#             assert data.__len__() == 1
#             assert data["1"]["cron_expression"] == "0 6 * * *"
#
#     @cndi_context_test
#     def test_cron_update_tool(self, test_agent: TestAgents):
#         agent = test_agent.agent
#         config = {"configurable": {"thread_id": "session-123"}}
#         cron_schedule = CronSchedule.model_validate(
#             {
#                 "cron_expression": "0 21 * * *",
#                 "id": "0aa95f00-3967-4ce0-8318-8d70f80b0056",
#                 "name": "cron_schedule",
#                 "subagent": {
#                     "agent_name": "general-purpose",
#                     "model": "openai:nvidia/nemotron-3-super-120b-a12b",
#                     "tools": [],
#                     "system_prompt": "You are a research assistant tasked with finding the latest news about technology and cyber security. Search the internet for recent articles, summarize key points, and provide a concise report.",
#                     "extra_config": {},
#                     "share_session": False,
#                     "session_id": None,
#                 },
#                 "task": "Research latest news about technology and cyber on the internet and provide a detailed summary with key points, sources, and potential implications.",
#                 "delivery": {
#                     "to": ["8705816265"],
#                     "channel": "telegram",
#                     "mode": "announce",
#                 },
#             }
#         )
#
#         with tinydb.TinyDB(os.environ.get("CRON_SCHEDULE_FILENAME")) as db:
#             db.insert(cron_schedule.model_dump(mode="json"))
#
#         user_query = "Update the cron schedule for 'cron_schedule' to send a message at 10 PM everyday with the content 'Updated message!'"
#         result = agent.invoke(
#             {
#                 "messages": [("user", user_query)],
#             },
#             config=config,
#         )
#
#         final_messages = list(
#             filter(lambda x: x["type"] == "text", result["messages"][-1].content)
#         )
#         assert final_messages.__len__() == 1
#         logger.info(f"Final message: {final_messages[0]}")
#         judge_result = test_agent.judge.invoke(
#             {
#                 "user_query": user_query,
#                 "response": final_messages[0]["text"],
#                 "criterias": "The response should confirm that the cron job has been updated successfully, and it should represent the correct cron schedule, include right task content of the schedule.",
#             }
#         )
#
#         assert judge_result.passed, f"Test failed: {judge_result.reasoning}"
#         assert judge_result.score >= 4, f"Test failed: {judge_result.score}"
#
#         assert os.path.exists(os.environ.get("CRON_SCHEDULE_FILENAME"))
#         with open(os.environ.get("CRON_SCHEDULE_FILENAME"), "r") as f:
#             data = json.load(f)["_default"]
#             assert data.__len__() == 1
#             assert data["1"]["cron_expression"] == "0 22 * * *"
#             assert data["1"]["id"] == "0aa95f00-3967-4ce0-8318-8d70f80b0056"
#
#     @cndi_context_test
#     def test_cron_list_tool(self, test_agent: TestAgents):
#         agent = test_agent.agent
#         config = {"configurable": {"thread_id": "session-123"}}
#         cron_schedule = CronSchedule.model_validate(
#             {
#                 "cron_expression": "0 21 * * *",
#                 "id": "0aa95f00-3967-4ce0-8318-8d70f80b0056",
#                 "name": "cron_schedule",
#                 "subagent": {
#                     "agent_name": "general-purpose",
#                     "model": "openai:nvidia/nemotron-3-super-120b-a12b",
#                     "tools": [],
#                     "system_prompt": "You are a research assistant tasked with finding the latest news about technology and cyber security. Search the internet for recent articles, summarize key points, and provide a concise report.",
#                     "extra_config": {},
#                     "share_session": False,
#                     "session_id": None,
#                 },
#                 "task": "Research latest news about technology and cyber on the internet and provide a detailed summary with key points, sources, and potential implications.",
#                 "delivery": {
#                     "to": ["8705816265"],
#                     "channel": "telegram",
#                     "mode": "announce",
#                 },
#             }
#         )
#
#         with tinydb.TinyDB(os.environ.get("CRON_SCHEDULE_FILENAME")) as db:
#             db.insert(cron_schedule.model_dump(mode="json"))
#
#         user_query = "What are the cron jobs scheduled?"
#         result = agent.invoke(
#             {
#                 "messages": [("user", user_query)],
#             },
#             config=config,
#         )
#
#         final_messages = list(
#             filter(lambda x: x["type"] == "text", result["messages"][-1].content)
#         )
#         assert final_messages.__len__() == 1
#         logger.info(f"Final message: {final_messages[0]}")
#         # judge_result = judge.invoke({
#         #     "user_query": user_query,
#         #     "response": final_messages[0]['text'],
#         #     "criterias": "The response should list all scheduled cron jobs and their details.",
#         # })
#
#         # assert judge_result.passed, f"Test failed: {judge_result.reasoning}"
#         # assert judge_result.score >= 4, f"Test failed: {judge_result.score}"
#
#         # assert os.path.exists(os.environ.get('CRON_SCHEDULE_FILENAME'))
#         # with open(os.environ.get('CRON_SCHEDULE_FILENAME'), 'r') as f:
#         #     data = json.load(f)
#         #     assert data.__len__() == 1
#         #     assert data[0]['cron_expression'] == "0 22 * * *"
#         #     assert data[0]['message'] == "Updated message!"
#         #     assert data[0]['name'] == "cron_schedule"
#         #     assert data[0]['id'] == "0aa95f00-3967-4ce0-8318-8d70f80b0056"
