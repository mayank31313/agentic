import asyncio
import os

from cndi.initializers import AppInitializer
from fastmcp import FastMCP

from agentic.agentic_mcp.gmail.tools import get_gmail_tools
from agentic.agentic_mcp.stable_diffusion.tools import LocalAiApi, get_image_tools

mcp = FastMCP("Agentic MCP")


def add_tools(tools=[]):
    for tool in tools:
        mcp.add_tool(tool)


def onComplete(localai_api: LocalAiApi):
    transport = os.getenv("AGENTIC_MCP_TRANSPORT", "http")
    host = os.getenv("AGENTIC_MCP_HOST", "127.0.0.1")
    port = int(os.getenv("AGENTIC_MCP_PORT", "8811"))

    creds_path = os.getenv("GOOGLE_CREDENTIALS_FILE")
    image_tools = get_image_tools(localai_api)
    add_tools(image_tools)
    add_tools(get_gmail_tools(creds_path))

    asyncio.run(mcp.run_async(transport=transport, host=host, port=port))


def main():
    """Main entry point for the agentic mcp."""
    from dotenv import load_dotenv

    load_dotenv()

    app = AppInitializer()
    app.componentScan("agentic.agentic_mcp")
    app.run(onComplete=onComplete)
