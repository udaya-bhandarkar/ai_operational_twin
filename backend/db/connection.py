"""Shared DuckDB connection factory — one hardened configuration for every connection.

Every DuckDB connection in the process should be opened through here.

Why one shared config: DuckDB refuses to open a second connection to the same file with a
different configuration while another is open ("Can't open a connection to same database
file with a different configuration"), so every caller in the process must agree.

Hardening:
- enable_external_access=False — blocks the file-system / network surface a text-to-SQL agent
  must never reach: read_text/read_csv on local files (e.g. `.env`), COPY ... TO, ATTACH,
  INSTALL/LOAD of extensions.
- lock_configuration=True — a query cannot turn the above back on with SET.
"""
import duckdb

from config.settings import settings

HARDENED_CONFIG = {"enable_external_access": False, "lock_configuration": True}


def read_only_connection() -> duckdb.DuckDBPyConnection:
    """Read-only connection — the database itself refuses writes."""
    return duckdb.connect(settings.duckdb_path, read_only=True, config=dict(HARDENED_CONFIG))


def write_connection() -> duckdb.DuckDBPyConnection:
    """Read-write connection — only for HITL-approved statements."""
    return duckdb.connect(settings.duckdb_path, config=dict(HARDENED_CONFIG))
