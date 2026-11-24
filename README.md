# bizops-agents — a business-agnostic multi-agent ops team

LangGraph **supervisor** + specialist **worker agents**, running on a free local **Ollama** model, using **MCP** for every tool.
Point it at any small business by swapping one YAML file (a *business profile*).

```
 owner ──► intake ──► SUPERVISOR ──► sales | inventory | finance | support | marketing  (workers)
                         ▲  │            each worker:  llm → approve(human gate) → MCP tools → llm …
                         └──┘ reports    FINISH ──► final answer
```

* **Supervisor pattern**: the supervisor LLM picks the next worker (JSON `{"next","instruction"}`, parsed leniently for small models), reads its report, then picks another or finishes. Max hand-offs capped by `supervisor.max_steps`.
* **MCP everywhere**: the built-in `business-db` MCP server (SQLite: items, customers, orders, expenses, tickets, outbox) is the default toolset. Add any other MCP server (filesystem, calendar, email, Slack…) under `mcp_servers:` in the profile and give workers its tools by name.
* **Human approval gate**: tools listed in `approval_required` never run until you approve. The gate runs in a side-effect-free graph node (LangGraph `interrupt`), so resume can't double-execute. You can approve some calls in a batch and reject others. Messages are only ever *drafted* to an outbox, never sent.
* **Business-agnostic**: `profiles/generic.yaml` and `profiles/coffee_shop.yaml` use the same code. A profile defines the business, vocabulary, policies, which agents exist, which tools each gets, scheduled automations and seed data.

## Quick start

### Browser-based Office HQ

The [public Office HQ demo](https://hafiz-fansuri.github.io/bizops-agents/) runs on GitHub Pages.
Ask the supervisor to check stock, summarize sales, open a support ticket, record an expense,
or draft a message. Supported changes pause for approval. Try
`Open a ticket for Alex Tan: Starter Pack delivery question` or
`Draft an email for Alex Tan: Your replacement is ready.`
The office highlights workers during routing and shows when an action needs approval.

Guests work with disposable in-memory demo records. To save records, chat history, and pending
approvals across sessions, use **Save workspace** to sign in with Supabase. Each account can
access its own workspace through row-level security. The database schema is in
`supabase/office_workspaces.sql`. The hosted supervisor uses rules for supported demo operations.
The Python app below uses Ollama for open-ended analysis and planning with the configured tools.

From the project directory, install the package and start the local server in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
$env:OLLAMA_MODEL = 'qwen3:1.7b' # Optional. Set this to an installed tool-calling model.
.\.venv\Scripts\python.exe -m bizops.office
```

Open the localhost link printed in the terminal. Pass `--port 8765` for a fixed port if it is available.
Select a desk to choose an agent for chat. The guided
scenarios work without Ollama and call the same MCP database tools used by the agents.
Start with **Check low stock**. Then approve the sample order, reject the proposed restock,
review finances, record an expense, close the sample support ticket, and save an email draft.
The ticket list and low-stock check let you see the effects of those decisions.

Free-form chat requires a local Ollama model. It uses the existing supervisor and pauses for
approval before configured writes. Both paths operate on the sample database. **Reset demo**
restores the original records and clears conversation state and pending approvals. The demo
database lives in a temporary directory and is discarded when the server exits normally.

### Command line

```bash
# 1. Ollama (free, local) + a tool-calling model
ollama serve &
ollama pull qwen2.5:7b-instruct          # or llama3.1:8b, qwen3:8b, mistral-nemo ...

# 2. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                       # optional; env vars shown inside

# 3. Use it
bizops init                                # creates data/business.db with demo data
bizops chat                                # talk to the team
bizops run "Which items are low on stock and what should I reorder?"
bizops --profile profiles/coffee_shop.yaml chat
bizops daemon                              # run the profile's cron automations (writes rejected unless --approvals approve)
pytest                                     # 11 tests, no Ollama needed (scripted fake model + real MCP server)
```
Try: `Create an order for Alex Tan: 2 Starter Packs` → the sales agent proposes `create_order(...)`, you see the exact call and press `y` or `n`.

## Make it fit YOUR business
1. Copy `profiles/generic.yaml`, edit `business`, `policies`, and `seed` (or load your own data into the SQLite DB; the schema is in `src/bizops/db.py`).
2. Rename/add/remove agents; each is just `description`, `prompt`, `tools`.
3. Need another system? Add an MCP server:
   ```yaml
   mcp_servers:
     files: {transport: stdio, command: npx, args: ["-y", "@modelcontextprotocol/server-filesystem", "./exports"]}
   ```
   then list its tool names in an agent's `tools` (and in `approval_required` if it writes).
4. Add new built-in tools in `src/bizops/mcp_servers/business_db.py` with `@mcp.tool()` — the type hints become the schema.

## Layout
```
profiles/            business profiles (the only thing you change per business)
src/bizops/graph.py  supervisor graph, worker subgraphs, approval gate
src/bizops/toolbox.py   starts MCP servers, returns LangChain tools
src/bizops/mcp_servers/business_db.py   built-in MCP server (read + write tools)
src/bizops/runtime.py   run_turn(), approvers, Ollama preflight, checkpointing (SQLite, per-thread memory)
src/bizops/cli.py       init | chat | run | daemon
tests/               scripted-LLM tests incl. approval, rejection, resume, repeat-worker, profile swap
```

## Choosing a model (important with small local models)
Workers need reliable **tool calling**; the supervisor needs to emit JSON. 7–8B models work for this routing size; if routing or arguments get flaky, set `OLLAMA_SUPERVISOR_MODEL` to a bigger model (e.g. 14B) while keeping a small worker model. Context is 8k (`llm.py`). Everything is `temperature=0`.

## Known limits / next steps
* Not yet run against a live Ollama model in this build — the tests use a scripted model. First run: try `bizops run "hi"` then a read-only question, and tune prompts in `prompts.py` / profile for your model.
* Auth/multi-user: it is a single-operator tool. SQLite DB is local. For several users put the MCP server behind real auth and Postgres.
* Add: Telegram/WhatsApp front-end, LangSmith-style tracing, evals on a fixed question set per profile.
