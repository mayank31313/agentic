# test_agent_tasks.py

# with open("golden_set.yaml") as f:
#     CASES = yaml.safe_load(f)

# @pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
# def test_golden_set(agent, case):
#     result = agent.invoke({"messages": [("user", case["input"])]})
#     tool_calls = {msg.name for msg in result["messages"] if hasattr(msg, "name") and msg.name}

#     for tool in case["expected_tools"]:
#         assert tool in tool_calls, f"Expected {tool} to be called"
#     for tool in case["forbidden_tools"]:
#         assert tool not in tool_calls, f"{tool} should not have been called"
