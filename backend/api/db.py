"""Read-only DuckDB access + scope filtering for the dashboard endpoints.

All dashboard queries read from the gold table `gold_operational_metrics`
built by src/data_pipeline/build_gold_layer.py.

Scope params (shared by every endpoint):
    view          — 'ceo' | 'factory' | 'department' granularity selector.
                    Confirmed (frontend designer): the dropdowns drive scoping —
                    factory view sends facility_id; department view sends
                    facility_id + department_id; ceo sends neither. So `view`
                    itself needs no server logic; the ids below do the filtering.
    facility_id   — optional exact-match filter on facility_id.
    department_id — optional exact-match filter on department_id.
"""
from contextlib import contextmanager

from db.connection import read_only_connection

GOLD = "gold_operational_metrics"


@contextmanager
def connect():
    """Open a short-lived read-only connection to the operational DB."""
    conn = read_only_connection()
    try:
        yield conn
    finally:
        conn.close()


def scope_where(facility_id: str | None, department_id: str | None) -> tuple[str, list]:
    """Build a WHERE clause + bound params from the scope filters.

    `view` is not applied server-side by design — the dropdowns send the ids
    (see module docstring). Returns ("", []) when unfiltered, else ("WHERE ...", [params]).
    """
    clauses: list[str] = []
    params: list = []
    if facility_id:
        clauses.append("facility_id = ?")
        params.append(facility_id)
    if department_id:
        clauses.append("department_id = ?")
        params.append(department_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def max_timestamp(conn) -> str | None:
    """Latest timestamp in the data. Windows anchor here, not wall-clock —
    the dataset is a fixed snapshot, so 'now' would return empty ranges."""
    row = conn.execute(f"SELECT MAX(timestamp) FROM {GOLD}").fetchone()
    return row[0].isoformat() if row and row[0] else None
