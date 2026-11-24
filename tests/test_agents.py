import pytest

from bizops.config import load_profile
from bizops.graph import build_graph, parse_decision, parse_route
from bizops.runtime import approve_all, reject_all, run_turn
from tests.fakes import FINISH, Scripted, call, route
from langchain_core.messages import AIMessage, ToolMessage


async def test_profiles_load():
    for p in ("profiles/generic.yaml", "profiles/coffee_shop.yaml"):
        prof = load_profile(p)
        assert prof["agents"] and prof["business"]["name"]


async def test_read_only_flow_uses_real_mcp_data(make_app):
    script = [route("inventory", "list low stock"), call("low_stock", {}),
              AIMessage(content="P-002 Standard Widget is low (6 left)."), FINISH, AIMessage(content="Restock Standard Widget.")]
    graph, llm, cm = await make_app(script)
    try:
        out = await run_turn(graph, "what's low on stock?", "t1", reject_all)  # reads never need approval
        assert out == "Restock Standard Widget."
        tool_msgs = [m for call_msgs in llm.seen for m in call_msgs if isinstance(m, ToolMessage)]
        assert tool_msgs and "P-002" in tool_msgs[0].content           # data really came through MCP
    finally:
        await cm.__aexit__(None, None, None)


async def test_write_is_gated_and_executes_when_approved(make_app, db):
    args = {"customer_id": 1, "lines": [{"sku": "P-001", "qty": 2}]}
    script = [route("sales", "create order"), call("create_order", args),
              AIMessage(content="Order created."), FINISH, AIMessage(content="Done.")]
    graph, llm, cm = await make_app(script)
    try:
        before = db("SELECT COUNT(*), (SELECT stock FROM items WHERE sku='P-001') FROM orders")[0]
        asked = []

        async def approver(p):
            asked.append(p)
            assert db("SELECT COUNT(*) FROM orders")[0][0] == before[0]   # nothing executed before approval
            return True

        assert await run_turn(graph, "order 2 starter packs for Alex", "t2", approver) == "Done."
        assert asked[0]["actions"][0]["tool"] == "create_order"
        after = db("SELECT COUNT(*), (SELECT stock FROM items WHERE sku='P-001') FROM orders")[0]
        assert after == (before[0] + 1, before[1] - 2)
        assert not llm.script                                          # resume did not re-run the LLM step
    finally:
        await cm.__aexit__(None, None, None)


async def test_rejected_write_does_nothing(make_app, db):
    script = [route("inventory", "restock"), call("adjust_stock", {"sku": "P-002", "delta": 50, "reason": "restock"}),
              AIMessage(content="Operator rejected; not restocked."), FINISH, AIMessage(content="Not done.")]
    graph, llm, cm = await make_app(script)
    try:
        stock = db("SELECT stock FROM items WHERE sku='P-002'")[0][0]
        assert await run_turn(graph, "restock widgets", "t3", reject_all) == "Not done."
        assert db("SELECT stock FROM items WHERE sku='P-002'")[0][0] == stock
        assert any("REJECTED" in m.content for ms in llm.seen for m in ms if isinstance(m, ToolMessage))
    finally:
        await cm.__aexit__(None, None, None)


async def test_same_worker_twice_and_partial_approval(make_app, db):
    s1 = {"sku": "P-002", "delta": 5, "reason": "a"}
    s2 = {"sku": "P-003", "delta": 5, "reason": "b"}
    two_calls = AIMessage(content="", tool_calls=[
        {"name": "adjust_stock", "args": s1, "id": "a", "type": "tool_call"},
        {"name": "adjust_stock", "args": s2, "id": "b", "type": "tool_call"}])
    script = [route("inventory", "first"), two_calls, AIMessage(content="one done"),
              route("inventory", "second"), call("adjust_stock", {"sku": "P-001", "delta": 1, "reason": "c"}, "z"),
              AIMessage(content="second done"), FINISH, AIMessage(content="ok")]
    graph, llm, cm = await make_app(script)
    try:
        s = {r[0]: r[1] for r in db("SELECT sku, stock FROM items")}
        decisions = iter([{"approved_ids": ["a"]}, True])

        async def approver(p):
            return next(decisions)

        assert await run_turn(graph, "restock", "t4", approver) == "ok"
        n = {r[0]: r[1] for r in db("SELECT sku, stock FROM items")}
        assert n["P-002"] == s["P-002"] + 5 and n["P-003"] == s["P-003"]   # only 'a' approved
        assert n["P-001"] == s["P-001"] + 1                                  # second invocation ran fresh
    finally:
        await cm.__aexit__(None, None, None)


async def test_tool_error_is_fed_back_to_model(make_app):
    script = [route("sales"), call("create_order", {"customer_id": 1, "lines": [{"sku": "NOPE", "qty": 1}]}),
              AIMessage(content="Unknown SKU."), FINISH, AIMessage(content="Could not.")]
    graph, llm, cm = await make_app(script)
    try:
        assert await run_turn(graph, "order nope", "t5", approve_all) == "Could not."
        assert any("unknown sku" in m.content for ms in llm.seen for m in ms if isinstance(m, ToolMessage))
    finally:
        await cm.__aexit__(None, None, None)


async def test_conversation_resets_reports_between_turns(make_app):
    script = [FINISH, AIMessage(content="Hi!"), route("finance"), call("financial_summary", {"days": 7}),
              AIMessage(content="Revenue X"), FINISH, AIMessage(content="Revenue is X")]
    graph, llm, cm = await make_app(script)
    try:
        assert await run_turn(graph, "hello", "t6", approve_all) == "Hi!"
        assert await run_turn(graph, "how are we doing financially?", "t6", approve_all) == "Revenue is X"
    finally:
        await cm.__aexit__(None, None, None)


async def test_coffee_profile_runs_same_engine(make_app):
    script = [route("sales"), call("list_items", {}), AIMessage(content="Kopi O RM6"), FINISH, AIMessage(content="Kopi O is RM6.")]
    graph, llm, cm = await make_app(script, profile="profiles/coffee_shop.yaml")
    try:
        assert "Kopi O" in await run_turn(graph, "menu?", "t7", approve_all)
    finally:
        await cm.__aexit__(None, None, None)


async def test_bad_profile_tool_name_fails_fast(settings):
    prof = load_profile("profiles/generic.yaml")
    prof["agents"]["sales"]["tools"].append("does_not_exist")
    with pytest.raises(ValueError, match="does_not_exist"):
        build_graph(prof, {}, Scripted(script=[], seen=[]))


def test_parse_route_is_forgiving():
    v = ["sales", "finance"]
    assert parse_route('{"next":"Sales","instruction":"x"}', v, False, "sales") == ("sales", "x")
    assert parse_route('Sure! ```json\n{"next": "finance", "instruction": "p&l"}\n```', v, False, "sales")[0] == "finance"
    assert parse_route("<think>hmm {x}</think>{\"next\":\"FINISH\"}", v, True, "sales")[0] == "FINISH"
    assert parse_route("I think finance should do it", v, False, "sales")[0] == "finance"
    assert parse_route("???", v, False, "sales")[0] == "sales" and parse_route("???", v, True, "sales")[0] == "FINISH"


def test_parse_decision_variants():
    ids = ["a", "b"]
    assert parse_decision(True, ids) == [] and parse_decision("y", ids) == []
    assert parse_decision(False, ids) == ids and parse_decision("no", ids) == ids
    assert parse_decision({"approved_ids": ["b"]}, ids) == ["a"] and parse_decision({"approve": True}, ids) == []
