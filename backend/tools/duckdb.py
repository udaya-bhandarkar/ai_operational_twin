import json

import duckdb
from langchain_core.tools import tool

from config.settings import settings

_MUTATION_KEYWORDS = {"insert", "update", "delete", "drop", "create", "alter", "truncate"}


def _conn():
    return duckdb.connect(settings.duckdb_path)


def _first_word(query: str) -> str:
    return query.strip().lower().split()[0] if query.strip() else ""


@tool
def duckdb_list_tables() -> str:
    """List all tables in the operational DuckDB database."""
    try:
        with _conn() as conn:
            rows = conn.execute("SHOW TABLES").fetchall()
        if not rows:
            return "No tables found in the database."
        return ", ".join(r[0] for r in rows)
    except Exception as e:
        return f"[duckdb_list_tables] Error: {e}"


@tool
def duckdb_schema(table_names: str) -> str:
    """Get schema and 3 sample rows for one or more tables. Pass comma-separated table names."""
    tables = [t.strip() for t in table_names.split(",") if t.strip()]
    if not tables:
        return "No table names provided."
    output = []
    try:
        with _conn() as conn:
            for table in tables:
                try:
                    schema_rows = conn.execute(
                        f"SELECT column_name, data_type FROM information_schema.columns "
                        f"WHERE table_name = '{table}' ORDER BY ordinal_position"
                    ).fetchall()
                    if not schema_rows:
                        output.append(f"Table '{table}': not found or no columns.")
                        continue
                    cols = "\n".join(f"  {col}: {dtype}" for col, dtype in schema_rows)
                    sample = conn.execute(f"SELECT * FROM {table} LIMIT 3").fetchall()
                    col_names = [r[0] for r in schema_rows]
                    sample_str = "\n".join(str(dict(zip(col_names, row))) for row in sample)
                    output.append(f"Table: {table}\nColumns:\n{cols}\nSample rows:\n{sample_str}")
                except Exception as e:
                    output.append(f"Table '{table}': error — {e}")
    except Exception as e:
        return f"[duckdb_schema] Connection error: {e}"
    return "\n\n".join(output)


@tool
def duckdb_query_checker(query: str) -> str:
    """Validate a SQL query before execution. Always call this before duckdb_query or duckdb_execute.
    Returns 'OK — read query' for SELECT, 'OK — write query' for mutations, or an error."""
    first = _first_word(query)
    is_mutation = first in _MUTATION_KEYWORDS

    label = "write query" if is_mutation else "read query"

    try:
        with _conn() as conn:
            conn.execute(f"EXPLAIN {query}")
        return f"OK — {label}."
    except Exception as e:
        return f"INVALID — {e}"


@tool
def duckdb_query(query: str) -> str:
    """Execute a read-only SELECT query against the operational DuckDB database.
    Always call duckdb_query_checker first. Rejects mutation statements.
    Results capped at 100 rows."""
    if _first_word(query) in _MUTATION_KEYWORDS:
        return (
            "[duckdb_query] Rejected — mutation statements are not allowed here. "
            "Use duckdb_execute for INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE."
        )
    try:
        with _conn() as conn:
            cursor = conn.execute(query)
            if cursor.description is None:
                return "Query returned no rows."
            col_names = [d[0] for d in cursor.description]
            rows = cursor.fetchmany(100)
        if not rows:
            return "Query returned no rows."
        results = [dict(zip(col_names, row)) for row in rows]
        output = json.dumps(results, indent=2, default=str)
        return output + f"\n[{len(rows)} row(s)]"
    except Exception as e:
        return f"[duckdb_query] Error: {e}"


@tool
def duckdb_execute(statement: str) -> str:
    """Execute a write statement (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE)
    against the operational DuckDB database. Requires human approval before execution —
    do not call this without first calling duckdb_query_checker. Rejects SELECT statements."""
    if _first_word(statement) not in _MUTATION_KEYWORDS:
        return (
            "[duckdb_execute] Rejected — only mutation statements allowed here. "
            "Use duckdb_query for SELECT."
        )
    try:
        with _conn() as conn:
            conn.execute(statement)
        return "Statement executed successfully."
    except Exception as e:
        return f"[duckdb_execute] Error: {e}"
