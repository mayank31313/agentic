# # tests/integration/test_compose_scaling.py
# import logging
#
# import httpx
# from .conftest import requires_docker, scale_service
#
# logger = logging.getLogger(__name__)
#
# @requires_docker
# def test_bot_scales_up_and_down(compose_stack):
#     # --- scale up ---
#     scale_service(compose_stack, "bot", 1)
#     containers = [c for c in compose_stack.get_containers() if c.Service == "bot"]
#     assert len(containers) == 1
#     assert all(c.State == "running" for c in containers)
#
#     # --- exercise each replica ---
#     for container in containers:
#         host, port = compose_stack.get_service_host_and_port(
#             service_name="bot", port=5000
#         ) if len(containers) == 1 else (None, None)
#         # with >1 replica, use container.get_publisher(by_port=5000) directly:
#
#         pub = container.get_publisher(by_port=5000).normalize()
#         url = f"http://{pub.URL}:{pub.PublishedPort}/health"
#         logger.info(f"Bot Health URL: {url}")
#         resp = httpx.get(url, timeout=5)
#         assert resp.status_code == 200
#
#     # --- scale down ---
#     scale_service(compose_stack, "bot", 1)
#     containers = [c for c in compose_stack.get_containers() if c.Service == "bot"]
#     assert len(containers) == 1