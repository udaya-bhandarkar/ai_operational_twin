import duckdb
import pytest

import middleware.dynamic_model as dynamic_model
from config.settings import settings


@pytest.fixture
def no_cost_routing(monkeypatch):
    """Keep dev_cost_router from swapping the scripted test model for a real one."""
    monkeypatch.setattr(dynamic_model, "_budget_model_loaded", True)
    monkeypatch.setattr(dynamic_model, "_budget_model", None)


@pytest.fixture
def ops_db(tmp_path, monkeypatch):
    """A throwaway operational DB with one table `t(a INT)`; returns its path."""
    path = tmp_path / "ops.db"
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE t (a INT)")
    monkeypatch.setattr(settings, "duckdb_path", str(path))
    return path


def table_rows(path) -> list:
    with duckdb.connect(str(path), read_only=True) as conn:
        return conn.execute("SELECT a FROM t ORDER BY a").fetchall()
