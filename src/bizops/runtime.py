from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from bizops.config import Settings, load_profile
from bizops.db import init_db
from bizops.graph import build_graph
from bizops.llm import get_llm
from bizops.toolbox import Toolbox

Approver = Callable[[dict], Awaitable[Any]]


async def run_turn(graph, text: str, thread_id: str, approver: Approver) -> str:
    """One user turn. Pauses on every approval request and resumes with the approver's decision."""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 80}
    inp: Any = {"messages": [HumanMessage(text)]}
    while True:
        out = await graph.ainvoke(inp, config)
        intr = out.get("__interrupt__")
        if not intr:
            return next((m.content for m in reversed(out["messages"]) if isinstance(m, AIMessage)), "")
        inp = Command(resume=await approver(intr[0].value))


async def approve_all(_: dict) -> bool:
    return True


async def reject_all(_: dict) -> bool:
    return False


async def ask_on_terminal(payload: dict) -> bool:
    print(f"\n⚠  [{payload['agent']}] wants to make changes:")
    for a in payload["actions"]:
        print(f"   - {a['tool']}({a['args']})")
    if not sys.stdin.isatty():
        print("   (non-interactive: rejected)")
        return False
    import asyncio

    ans = await asyncio.to_thread(input, "   approve? [y/N] ")
    return ans.strip().lower() in ("y", "yes")


def preflight_ollama(s: Settings) -> None:
    """Fail early with an actionable message instead of a deep connection traceback."""
    import json
    import urllib.request

    try:
        tags = json.load(urllib.request.urlopen(f"{s.ollama_url}/api/tags", timeout=3))
    except Exception as e:
        raise SystemExit(f"Ollama is not reachable at {s.ollama_url} ({type(e).__name__}).\n"
                         f"  Start it:  ollama serve\n  Get a model:  ollama pull {s.model}") from None
    have = {m["name"] for m in tags.get("models", [])}
    for need in {s.model, s.supervisor_model} - {None}:
        if need not in have and f"{need}:latest" not in have:
            raise SystemExit(f"Model '{need}' not installed. Run:  ollama pull {need}\n  (installed: {sorted(have) or 'none'})")


@asynccontextmanager
async def open_app(settings: Settings, llm=None, supervisor_llm=None):
    """Bring up DB, MCP tools, checkpointer and the compiled graph."""
    if llm is None:
        preflight_ollama(settings)
    profile = load_profile(settings.profile_path)
    init_db(settings.db_path, profile.get("seed"))
    async with Toolbox(profile, settings.db_path) as tb, AsyncSqliteSaver.from_conn_string(settings.checkpoint_db) as cp:
        graph = build_graph(profile, tb.tools, llm or get_llm(settings),
                            supervisor_llm or (llm if llm else get_llm(settings, "supervisor")), cp)
        yield graph, profile
