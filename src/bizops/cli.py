from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path

from bizops.config import Settings, load_profile
from bizops.db import init_db
from bizops.runtime import approve_all, ask_on_terminal, open_app, reject_all, run_turn


def _approver(mode: str):
    return {"ask": ask_on_terminal, "approve": approve_all, "reject": reject_all}[mode]


async def chat(s: Settings, mode: str) -> None:
    thread = f"chat-{uuid.uuid4().hex[:8]}"
    async with open_app(s) as (graph, profile):
        print(f"{profile['business']['name']} - ops team ready ({', '.join(profile['agents'])}). Ctrl-C / 'exit' to quit.\n")
        while True:
            try:
                q = await asyncio.to_thread(input, "you> ")
            except (EOFError, KeyboardInterrupt):
                return
            if q.strip().lower() in ("exit", "quit"):
                return
            if q.strip():
                print("\n" + await run_turn(graph, q, thread, _approver(mode)) + "\n")


async def run_once(s: Settings, task: str, mode: str) -> None:
    async with open_app(s) as (graph, _):
        print(await run_turn(graph, task, f"task-{uuid.uuid4().hex[:8]}", _approver(mode)))


async def daemon(s: Settings, mode: str) -> None:
    """Run the profile's `automations` on their cron schedule (default: writes are rejected unless --approvals approve)."""
    from croniter import croniter

    profile = load_profile(s.profile_path)
    jobs = [{**j, "it": croniter(j["cron"], datetime.now())} for j in profile["automations"]]
    if not jobs:
        print("no automations in profile")
        return
    nxt = {j["name"]: j["it"].get_next(float) for j in jobs}
    print("scheduled:", {j["name"]: j["cron"] for j in jobs})
    async with open_app(s) as (graph, _):
        while True:
            for j in jobs:
                if time.time() >= nxt[j["name"]]:
                    nxt[j["name"]] = j["it"].get_next(float)
                    print(f"\n=== {j['name']} @ {datetime.now():%F %T} ===")
                    out = await run_turn(graph, j["task"], f"auto-{j['name']}-{int(time.time())}", _approver(mode))
                    print(out)
                    Path("data/reports").mkdir(parents=True, exist_ok=True)
                    Path(f"data/reports/{j['name']}-{datetime.now():%Y%m%d-%H%M}.txt").write_text(out)
            await asyncio.sleep(20)


def main() -> None:
    ap = argparse.ArgumentParser(prog="bizops", description="Multi-agent business operations assistant")
    ap.add_argument("--profile", help="path to business profile YAML (default $BIZOPS_PROFILE)")
    ap.add_argument("--approvals", choices=["ask", "approve", "reject"], default="ask",
                    help="what to do when an agent wants to change data (default: ask; non-interactive asks => reject)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create + seed the database from the profile")
    sub.add_parser("chat", help="interactive chat with the team")
    r = sub.add_parser("run", help="run one task and exit")
    r.add_argument("task")
    sub.add_parser("daemon", help="run scheduled automations from the profile")
    a = ap.parse_args()

    s = Settings()
    if a.profile:
        s.profile_path = a.profile
    if a.cmd == "init":
        init_db(s.db_path, load_profile(s.profile_path).get("seed"))
        print(f"database ready at {s.db_path}")
    elif a.cmd == "chat":
        asyncio.run(chat(s, a.approvals))
    elif a.cmd == "run":
        asyncio.run(run_once(s, a.task, a.approvals))
    else:
        asyncio.run(daemon(s, "reject" if a.approvals == "ask" else a.approvals))


if __name__ == "__main__":
    main()
