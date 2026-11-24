"""Opens every MCP server named in the profile (built-in business DB + any extra ones) and returns LangChain tools."""
from __future__ import annotations

import sys
from contextlib import AsyncExitStack

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


def server_configs(profile: dict, db_path: str) -> dict:
    cfg = {"business": {"transport": "stdio", "command": sys.executable,
                        "args": ["-m", "bizops.mcp_servers.business_db"], "env": {"BIZOPS_DB": db_path, "PATH": __import__("os").environ.get("PATH", ""), "PYTHONPATH": __import__("os").environ.get("PYTHONPATH", "")}}}
    cfg.update(profile.get("mcp_servers") or {})
    return cfg


class Toolbox:
    """async with Toolbox(profile, db) as tb:  tb.tools -> {name: tool}"""

    def __init__(self, profile: dict, db_path: str):
        self._cfg, self._stack = server_configs(profile, db_path), AsyncExitStack()
        self.tools: dict[str, BaseTool] = {}

    async def __aenter__(self) -> Toolbox:
        client = MultiServerMCPClient(self._cfg)
        for name in self._cfg:
            session = await self._stack.enter_async_context(client.session(name))  # one persistent process per server
            for t in await load_mcp_tools(session):
                self.tools[t.name] = t
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()
