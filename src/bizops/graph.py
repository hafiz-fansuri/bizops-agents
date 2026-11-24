"""LangGraph supervisor + worker agents with a human-approval gate for write actions.

            ┌────────── intake ──► supervisor ──► FINISH ──► final ──► END
            │                        ▲   │ next=<agent>
            │                        │   ▼
            │                   (report) worker subgraph:  llm ─► approve(interrupt) ─► tools ─► llm …
            └─ worker subgraphs share nothing but the report they hand back
"""
from __future__ import annotations

import json
import re
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from bizops import prompts

MAX_TOOL_LOOPS = 6
FINISH = "FINISH"


# ----------------------------------------------------------------------------- state
def merge_reports(old: list[dict] | None, new: list[dict] | None) -> list[dict]:
    if new and new[0].get("_reset"):
        return []
    return (old or []) + (new or [])


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    next: str
    instruction: str
    steps: int
    reports: Annotated[list[dict], merge_reports]


class WorkerState(TypedDict, total=False):
    scratch: Annotated[list[AnyMessage], add_messages]
    rejected: list[str]
    loops: int


# ----------------------------------------------------------------------------- helpers
def _text(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in x)
    return json.dumps(x, default=str) if isinstance(x, (dict, tuple)) else str(x)


def _strip_think(s: str) -> str:
    return re.sub(r"<think>.*?</think>", "", s, flags=re.S).strip()


def parse_route(text: str, valid: list[str], has_reports: bool, default: str) -> tuple[str, str]:
    """Robustly extract {"next","instruction"} from small-model output; never raises."""
    text = _strip_think(text)
    for m in re.finditer(r"\{.*?\}", text, flags=re.S):
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        nxt = str(d.get("next") or d.get("agent") or "").strip()
        if nxt.upper() == FINISH:
            return FINISH, ""
        if nxt.lower() in valid:
            return nxt.lower(), str(d.get("instruction") or d.get("task") or "").strip()
    low = text.lower()
    if "finish" in low:
        return FINISH, ""
    for v in valid:  # model rambled but named an agent
        if re.search(rf"\b{re.escape(v)}\b", low):
            return v, ""
    return (FINISH, "") if has_reports else (default, "")


def final_text(scratch: list[AnyMessage]) -> str:
    for m in reversed(scratch):
        if isinstance(m, AIMessage) and not m.tool_calls and _text(m.content).strip():
            return _strip_think(_text(m.content))
    tools = [_text(m.content) for m in scratch if isinstance(m, ToolMessage)]
    return ("(agent hit its step limit) Last tool output: " + tools[-1][:600]) if tools else "(no result)"


def parse_decision(decision: Any, ids: list[str]) -> list[str]:
    """Return the tool-call ids that were REJECTED. Accepts bool/str/dict/list from the approver."""
    if isinstance(decision, dict):
        if "approved_ids" in decision:
            return [i for i in ids if i not in set(decision["approved_ids"])]
        decision = decision.get("approve", False)
    if isinstance(decision, list):
        return [i for i in ids if i not in set(decision)]
    ok = decision if isinstance(decision, bool) else str(decision).strip().lower() in ("y", "yes", "approve", "approved", "true", "ok")
    return [] if ok else list(ids)


def business_ctx(profile: dict) -> dict:
    b = profile["business"]
    v = {"item": "item", "customer": "customer", "order": "order", **b.get("vocabulary", {})}
    pol = " ".join(f"- {p}" for p in b.get("policies", []))
    return {"name": b["name"], "description": b.get("description", ""), "currency": b.get("currency", ""),
            "policies": pol, **v}


# ----------------------------------------------------------------------------- worker
def build_worker(name: str, spec: dict, tools: list[BaseTool], llm: BaseChatModel, write_names: set[str], ctx: dict):
    by_name = {t.name: t for t in tools}
    model = llm.bind_tools(tools) if tools else llm
    system = SystemMessage(prompts.WORKER.format(prompt=spec["prompt"], **ctx))

    async def call_model(state: WorkerState) -> dict:
        resp = await model.ainvoke([system, *state["scratch"]])
        return {"scratch": [resp], "loops": state.get("loops", 0) + 1}

    def route(state: WorkerState) -> str:
        last = state["scratch"][-1]
        return "approve" if getattr(last, "tool_calls", None) and state.get("loops", 0) <= MAX_TOOL_LOOPS else END

    async def approve(state: WorkerState) -> dict:
        # NO side effects before interrupt(): this node is re-executed from the top when the run resumes.
        calls = state["scratch"][-1].tool_calls
        pending = [tc for tc in calls if tc["name"] in write_names]
        if not pending:
            return {"rejected": []}
        decision = interrupt({"agent": name, "actions": [{"id": tc["id"], "tool": tc["name"], "args": tc["args"]} for tc in pending]})
        return {"rejected": parse_decision(decision, [tc["id"] for tc in pending])}

    async def run_tools(state: WorkerState) -> dict:
        rejected, out = set(state.get("rejected") or []), []
        for tc in state["scratch"][-1].tool_calls:
            if tc["id"] in rejected:
                content = "REJECTED by the operator. The action was NOT performed. Do not retry; tell the user."
            elif tc["name"] not in by_name:
                content = f"Unknown tool '{tc['name']}'. Available tools: {', '.join(by_name)}"
            else:
                try:
                    content = _text(await by_name[tc["name"]].ainvoke(tc["args"]))
                except Exception as e:  # let the model see and recover from bad arguments
                    content = f"Tool error: {type(e).__name__}: {e}"
            out.append(ToolMessage(content=content, tool_call_id=tc["id"], name=tc["name"]))
        return {"scratch": out}

    g = StateGraph(WorkerState)
    g.add_node("llm", call_model)
    g.add_node("approve", approve)
    g.add_node("tools", run_tools)
    g.add_edge(START, "llm")
    g.add_conditional_edges("llm", route, {"approve": "approve", END: END})
    g.add_edge("approve", "tools")
    g.add_edge("tools", "llm")
    return g.compile()


# ----------------------------------------------------------------------------- supervisor graph
def _last_human(msgs: list[AnyMessage]) -> str:
    return next((_text(m.content) for m in reversed(msgs) if isinstance(m, HumanMessage)), "")


def _render_reports(reports: list[dict], limit: int = 900) -> str:
    return "\n".join(f"[{r['agent']}] task: {r['task']}\n  result: {r['result'][:limit]}" for r in reports) or "(none yet)"


def build_graph(profile: dict, tools: dict[str, BaseTool], llm: BaseChatModel,
                supervisor_llm: BaseChatModel | None = None, checkpointer=None):
    supervisor_llm = supervisor_llm or llm
    ctx = business_ctx(profile)
    agents: dict[str, dict] = profile["agents"]
    valid = list(agents)
    write_names = set(profile.get("approval_required", []))
    max_steps = profile["supervisor"]["max_steps"]
    default_agent = profile["supervisor"]["default_agent"]

    missing = {a: [t for t in s["tools"] if t not in tools] for a, s in agents.items()}
    missing = {a: m for a, m in missing.items() if m}
    if missing:
        raise ValueError(f"profile references tools no MCP server provides: {missing}. Available: {sorted(tools)}")

    roster = "\n".join(f"- {n}: {s['description']}" for n, s in agents.items())
    sup_system = SystemMessage(prompts.SUPERVISOR.format(roster=roster, **ctx))
    final_system = SystemMessage(prompts.FINAL.format(**ctx))

    async def intake(state: State) -> dict:
        return {"reports": [{"_reset": True}], "steps": 0, "next": "", "instruction": ""}

    async def supervisor(state: State) -> dict:
        reports = state.get("reports", [])
        if state.get("steps", 0) >= max_steps:
            return {"next": FINISH}
        history = "\n".join(f"{'Owner' if isinstance(m, HumanMessage) else 'Team'}: {_text(m.content)[:300]}"
                            for m in state["messages"][-7:-1])
        user = (f"Earlier conversation:\n{history or '(none)'}\n\nOwner's request: {_last_human(state['messages'])}\n\n"
                f"Reports so far:\n{_render_reports(reports)}\n\nJSON decision:")
        resp = await supervisor_llm.ainvoke([sup_system, HumanMessage(user)])
        nxt, instr = parse_route(_text(resp.content), valid, bool(reports), default_agent)
        if nxt != FINISH and any(r["agent"] == nxt and r["task"] == instr for r in reports):
            nxt = FINISH  # identical repeat -> stop looping
        return {"next": nxt, "instruction": instr or _last_human(state["messages"])}

    def make_node(name: str):
        worker = build_worker(name, agents[name], [tools[t] for t in agents[name]["tools"]], llm, write_names, ctx)

        async def node(state: State, config) -> dict:
            prompt = (f"Owner's original request: {_last_human(state['messages'])}\n"
                      f"Your task: {state['instruction']}\n"
                      f"Other team reports so far:\n{_render_reports(state.get('reports', []), 400)}")
            out = await worker.ainvoke({"scratch": [HumanMessage(prompt)], "loops": 0}, config)
            return {"reports": [{"agent": name, "task": state["instruction"], "result": final_text(out["scratch"])}],
                    "steps": state.get("steps", 0) + 1}
        return node

    async def final(state: State) -> dict:
        reports = state.get("reports", [])
        user = f"Owner's request: {_last_human(state['messages'])}\n\nTeam reports:\n{_render_reports(reports, 1500)}"
        resp = await supervisor_llm.ainvoke([final_system, *state["messages"][-5:-1], HumanMessage(user)])
        return {"messages": [AIMessage(content=_strip_think(_text(resp.content)))]}

    g = StateGraph(State)
    g.add_node("intake", intake)
    g.add_node("supervisor", supervisor)
    g.add_node("final", final)
    for n in valid:
        g.add_node(n, make_node(n))
        g.add_edge(n, "supervisor")
    g.add_edge(START, "intake")
    g.add_edge("intake", "supervisor")
    g.add_conditional_edges("supervisor", lambda s: s["next"], {**{n: n for n in valid}, FINISH: "final"})
    g.add_edge("final", END)
    return g.compile(checkpointer=checkpointer)
