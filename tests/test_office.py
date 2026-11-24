from contextlib import closing

import pytest

from bizops.config import Settings
from bizops.db import connect
from bizops.office import Office, SCENARIOS


@pytest.mark.asyncio
async def test_demo_scenarios_and_reset(tmp_path):
    office = Office(Settings(), tmp_path)
    for scenario in SCENARIOS:
        reply = await office.perform({"kind": "demo", "scenario": scenario})
        if "approval" not in reply:
            assert reply["result"]
            continue
        approval = reply["approval"]
        assert (await office.perform({"kind": "info"}))["approval"] == approval
        if scenario == "order":
            with closing(connect(office.settings.db_path)) as db:
                assert db.execute("SELECT stock FROM items WHERE sku='P-001'").fetchone()[0] == 40
        await office.perform({"kind": "decision", "id": approval["id"], "approve": scenario != "adjust"})
        with pytest.raises(ValueError, match="no longer pending"):
            await office.perform({"kind": "decision", "id": approval["id"], "approve": True})

    with closing(connect(office.settings.db_path)) as db:
        assert dict(db.execute("SELECT sku, stock FROM items").fetchall())["P-001"] == 38
        assert db.execute("SELECT stock FROM items WHERE sku='P-002'").fetchone()[0] == 6
        assert db.execute("SELECT COUNT(*) FROM expenses WHERE note='Demo supplies'").fetchone()[0] == 1
        assert db.execute("SELECT status FROM tickets WHERE id=1").fetchone()[0] == "closed"
        assert db.execute("SELECT status FROM outbox").fetchone()[0] == "draft"

    await office.perform({"kind": "reset"})
    with closing(connect(office.settings.db_path)) as db:
        assert db.execute("SELECT stock FROM items WHERE sku='P-001'").fetchone()[0] == 40
        assert db.execute("SELECT status FROM tickets WHERE id=1").fetchone()[0] == "open"
        assert db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
