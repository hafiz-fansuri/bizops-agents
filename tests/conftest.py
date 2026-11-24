import sqlite3

import pytest

from bizops.config import Settings
from bizops.runtime import open_app
from tests.fakes import Scripted


@pytest.fixture()
def settings(tmp_path):
    return Settings(profile_path="profiles/generic.yaml", db_path=str(tmp_path / "b.db"),
                    checkpoint_db=str(tmp_path / "cp.db"))


@pytest.fixture()
def make_app(settings):
    async def _make(script, profile=None):
        llm = Scripted(script=list(script), seen=[])
        if profile:
            settings.profile_path = profile
        cm = open_app(settings, llm=llm)
        graph, prof = await cm.__aenter__()
        return graph, llm, cm
    return _make


@pytest.fixture()
def db(settings):
    def q(sql, *a):
        with sqlite3.connect(settings.db_path) as c:
            return c.execute(sql, a).fetchall()
    return q
