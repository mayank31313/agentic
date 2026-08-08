# # test_agent_tools.py

# def test_agent_calls_search_before_cancel(agent):
#     result = agent.invoke({
#         "messages": [("user", "Cancel my order, customer id is cust_123")]
#     })

#     tool_calls = [
#         msg.name for msg in result["messages"]
#         if hasattr(msg, "name") and msg.name
#     ]

#     assert "search_orders" in tool_calls
#     assert "cancel_order" in tool_calls
#     assert tool_calls.index("search_orders") < tool_calls.index("cancel_order")


# def test_agent_does_not_cancel_without_confirmation(agent):
#     result = agent.invoke({
#         "messages": [("user", "What's the status of my order? customer id cust_123")]
#     })
#     tool_calls = [msg.name for msg in result["messages"] if hasattr(msg, "name") and msg.name]

#     assert "cancel_order" not in tool_calls  # shouldn't cancel on a status check
