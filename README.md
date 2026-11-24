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

The [hosted Office HQ](https://hafiz-fansuri.github.io/bizops-agents/) uses Supabase for authenticated
conversations, agent assignments, and business records. Sign in and add your organization's information
under **Business records**. When you send a message, the supervisor can delegate to up to three
specialists and bring their work back as a single reply. The office displays each agent's status from
Supabase. Specialists analyze the supplied information, plan work, and draft material.

The production schema in `supabase/office_production.sql` seeds the five specialist roles. Each user's
records and conversations start empty, and row-level security scopes reads to the signed-in account.
Earlier demo workspaces use a separate legacy table.

Set the following [Edge Function secrets](https://supabase.com/docs/guides/functions/secrets) in the
Supabase project. Keep them out of the browser and repository.

| Secret | Value |
| --- | --- |
| `OFFICE_ALLOWED_EMAILS` | Comma-separated verified account emails allowed to invoke the model |
| `OFFICE_LLM_URL` | Reachable HTTPS URL for an OpenAI-compatible `/chat/completions` endpoint |
| `OFFICE_LLM_MODEL` | Model ID served by that endpoint |
| `OFFICE_LLM_KEY` | API key if that endpoint requires one |

To use Nemotron 3.5 Lightning online, point these settings to an authenticated, hosted Ollama-compatible
endpoint that serves the model. The hosted supervisor sends the user's request and relevant account data
to the configured provider. Supabase stores the run and processes it in the background after the user
sends the message.

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

To use NVIDIA Nemotron 3.5 Lightning for the supervisor and workers on a machine
that can run the model:

```powershell
ollama pull nemotron-3.5-lightning
$env:OLLAMA_MODEL = 'nemotron-3.5-lightning'
.\.venv\Scripts\python.exe -m bizops.office
```

Use the printed localhost link. If `OLLAMA_SUPERVISOR_MODEL` is set, that value
selects a separate supervisor model. The hosted app uses the model configured in
the Supabase Edge Function secrets.

The local agent prompts use [the capability catalog](src/bizops/capabilities.json).
It distinguishes supported, partial, and planned jobs. The runtime checks each
entry against the tools assigned by the active business profile. Profile tool
permissions and write approvals apply to all models.

Workers need reliable **tool calling**; the supervisor needs to emit JSON. 7–8B models work for this routing size; if routing or arguments get flaky, set `OLLAMA_SUPERVISOR_MODEL` to a bigger model (e.g. 14B) while keeping a small worker model. Context is 8k (`llm.py`). Everything is `temperature=0`.

## Known limits / next steps
* Not yet run against a live Ollama model in this build — the tests use a scripted model. First run: try `bizops run "hi"` then a read-only question, and tune prompts in `prompts.py` / profile for your model.
* Auth/multi-user: it is a single-operator tool. SQLite DB is local. For several users put the MCP server behind real auth and Postgres.
* Add: Telegram/WhatsApp front-end, LangSmith-style tracing, evals on a fixed question set per profile.
