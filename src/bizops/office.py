"""Local Office HQ and reproducible demo scenarios."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from bizops.config import Settings, load_profile
from bizops.db import init_db
from bizops.runtime import open_app
from bizops.toolbox import Toolbox

UI = Path(__file__).with_name("office_ui")
SCENARIOS = {
    "stock": ("inventory", "Check low stock", "low_stock", {}),
    "order": ("sales", "Order two Starter Packs for Alex", "create_order",
              {"customer_id": 1, "lines": [{"sku": "P-001", "qty": 2}]}),
    "adjust": ("inventory", "Propose adding 20 Standard Widgets", "adjust_stock",
               {"sku": "P-002", "delta": 20, "reason": "Demo restock"}),
    "finance": ("finance", "Review 30-day finances", "financial_summary", {"days": 30}),
    "expense": ("finance", "Record a $25 supplies expense", "record_expense",
                {"category": "supplies", "amount": 25, "note": "Demo supplies"}),
    "tickets": ("support", "Review support tickets", "list_tickets", {"status": "all"}),
    "resolve": ("support", "Close Alex’s delivery ticket", "update_ticket",
                {"ticket_id": 1, "status": "closed", "reply_draft": "We’ve resolved your delivery issue."}),
    "draft": ("marketing", "Draft an email for Alex", "draft_message",
              {"customer_id": 1, "channel": "email", "text": "Hi Alex, our Starter Pack is back in stock."}),
}


class Office:
    def __init__(self, settings: Settings, directory: Path):
        self.settings = settings
        self.directory = directory
        self.profile = load_profile(settings.profile_path)
        self.reset()

    def reset(self):
        # Reuse the directory only after all request-owned SQLite connections close.
        for filename in ("business.db", "checkpoints.db"):
            for suffix in ("", "-shm", "-wal", "-journal"):
                (self.directory / (filename + suffix)).unlink(missing_ok=True)
        self.settings = replace(self.settings, db_path=str(self.directory / "business.db"),
                                checkpoint_db=str(self.directory / "checkpoints.db"))
        init_db(self.settings.db_path, self.profile.get("seed"))
        self.pending = None
        self.thread = uuid4().hex
        return self.info()

    def info(self):
        return {"business": self.profile["business"], "agents": {
            agent: spec["description"] for agent, spec in self.profile["agents"].items()
        }, "scenarios": [{"id": key, "agent": agent, "label": label}
                          for key, (agent, label, _, _) in SCENARIOS.items()]}

    async def perform(self, body):
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object.")
        kind = body.get("kind")
        if kind == "info":
            return {**self.info(), "approval": self.pending[0] if self.pending else None}
        if kind == "reset":
            return self.reset()
        if kind == "decision":
            if not self.pending or body.get("id") != self.pending[0]["id"] or type(body.get("approve")) is not bool:
                raise ValueError("This approval is no longer pending.")
            _, scenario = self.pending
            self.pending = None
            if scenario is None:
                return await self.live(Command(resume=body["approve"]))
            if not body["approve"]:
                return {"message": "Rejected. No records changed."}
            return await self.demo_tool(scenario)
        if self.pending:
            raise ValueError("Approve or reject the pending action first.")
        if kind == "demo":
            scenario = body.get("scenario")
            if not isinstance(scenario, str) or scenario not in SCENARIOS:
                raise ValueError("Choose a demo scenario.")
            agent, _, tool, args = SCENARIOS[scenario]
            if tool in self.profile["approval_required"]:
                return self.approval({"agent": agent, "actions": [{"tool": tool, "args": args}]}, scenario)
            return await self.demo_tool(scenario)
        if kind == "chat":
            message = body.get("message")
            agent = body.get("agent")
            if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                raise ValueError("Enter a message of up to 4,000 characters.")
            if not isinstance(agent, str) or agent not in self.profile["agents"]:
                raise ValueError("Select an agent.")
            prompt = f"Please route this to {agent} if appropriate.\n{message.strip()}"
            return await self.live({"messages": [HumanMessage(prompt)]})
        raise ValueError("Unknown Office HQ action.")

    def approval(self, payload, scenario=None):
        approval = {**payload, "id": uuid4().hex}
        self.pending = (approval, scenario)
        return {"approval": approval}

    async def demo_tool(self, scenario):
        _, _, tool, args = SCENARIOS[scenario]
        async with Toolbox(self.profile, self.settings.db_path) as toolbox:
            return {"result": await toolbox.tools[tool].ainvoke(args)}

    async def live(self, request):
        try:
            async with open_app(self.settings) as (graph, _):
                config = {"configurable": {"thread_id": self.thread}, "recursion_limit": 80}
                output = await graph.ainvoke(request, config)
        except SystemExit as error:
            raise ValueError(str(error)) from error
        if interrupts := output.get("__interrupt__"):
            return self.approval(interrupts[0].value)
        return {"message": output["messages"][-1].content}


class OfficeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        assets = {"/": ("index.html", "text/html"), "/office.css": ("office.css", "text/css"),
                  "/office.js": ("office.js", "text/javascript")}
        if self.path in assets:
            file, content_type = assets[self.path]
            self.reply((UI / file).read_bytes(), content_type)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/office":
            self.send_error(404)
            return
        if (self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"
                or self.headers.get("Origin", f"http://127.0.0.1:{self.server.server_port}")
                != f"http://127.0.0.1:{self.server.server_port}"
                or self.headers.get_content_type() != "application/json"):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768:
                raise ValueError("Invalid request size.")
            result = asyncio.run(self.server.office.perform(json.loads(self.rfile.read(length))))
            self.reply(json.dumps(result, ensure_ascii=False).encode(), "application/json")
        except ValueError as error:
            self.reply(json.dumps({"error": str(error)}).encode(), "application/json", 400)
        except Exception:
            import traceback

            traceback.print_exc()
            self.reply(b'{"error":"The request failed. Check the Office HQ terminal."}', "application/json", 500)

    def reply(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the local BizOps Office HQ demo.")
    parser.add_argument("--port", type=int, default=0, help="Loopback port (default: automatically select one)")
    args = parser.parse_args()
    # The guided scenarios are pinned to the known sample business and sample IDs.
    settings = replace(Settings(), profile_path="profiles/generic.yaml")
    with TemporaryDirectory(prefix="bizops-office-") as directory, HTTPServer(
        ("127.0.0.1", args.port), OfficeHandler
    ) as server:
        server.office = Office(settings, Path(directory))
        print(f"Office HQ is ready at http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
