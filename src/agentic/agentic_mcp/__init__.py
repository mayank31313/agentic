import os

from cndi.initializers import AppInitializer
from fastmcp import FastMCP

from agentic.mcp.stable_diffusion.tools import get_image_tools, LocalAiApi

mcp = FastMCP("Agentic MCP")

@mcp.tool
def get_user_data() -> dict:
    """Get user data."""
    return {"name": "Alice", "age": 30, "active": True}

def onComplete(localai_api: LocalAiApi):
    transport = os.getenv("AGENTIC_MCP_TRANSPORT", "http"),
    host = os.getenv("AGENTIC_MCP_HOST", "127.0.0.1"),
    port = int(os.getenv("AGENTIC_MCP_PORT", "8811"))

    image_tools = get_image_tools(localai_api)
    for image_tool in image_tools:
        mcp.add_tool(image_tool)

    mcp.run(transport=transport,
            host=host, port=port)
def main():
    """Main entry point for the agentic mcp."""
    app = AppInitializer()
    app.componentScan("cndi")
    app.componentScan("agentic.mcp")
    app.run()

