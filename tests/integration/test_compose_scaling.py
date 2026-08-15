# tests/integration/test_compose_scaling.py
import httpx
import pytest

from .conftest import requires_docker, scale_service


@requires_docker
def test_mcp_scales_up_and_down(compose_stack):
    # --- scale up ---
    scale_service(compose_stack, "mcp", 3)
    containers = [c for c in compose_stack.get_containers() if c.Service == "mcp"]
    assert len(containers) == 3
    assert all(c.State == "running" for c in containers)

    # --- exercise each replica ---
    for container in containers:
        host, port = compose_stack.get_service_host_and_port(
            service_name="mcp", port=8811
        ) if len(containers) == 1 else (None, None)
        # with >1 replica, use container.get_publisher(by_port=8811) directly:
        pub = container.get_publisher(by_port=8811).normalize()
        resp = httpx.get(f"http://{pub.URL}:{pub.PublishedPort}/health", timeout=5)
        assert resp.status_code == 200

    # --- scale down ---
    scale_service(compose_stack, "mcp", 1)
    containers = [c for c in compose_stack.get_containers() if c.Service == "mcp"]
    assert len(containers) == 1