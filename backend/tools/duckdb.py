"""DuckDB tools with defense-in-depth against SQL injection and write-bypass.

Security model (aligned with the OWASP Top 10 for LLM Applications):
1. AST classification (sqlglot) with ALLOWLISTS — a statement is a "read" only if its AST is
   a known query type (SELECT, UNION, DESCRIBE, ...), and a "write" only if it is known DML/DDL.
   Everything else (COPY, ATTACH, INSTALL, SET, PRAGMA, unparsed commands) is "unsupported"
   and refused by both tools. Catches bypasses like `WITH t AS (SELECT 1) DELETE FROM x`,
   which starts with "with" and would pass a first-word check.
2. Hardened connections (db/connection.py) — read tools use `read_only=True`, and every
   connection disables external access, so even a misclassified statement can neither
   mutate the database nor read/write local files.
3. Parameterized metadata queries + identifier allowlisting — `duckdb_schema` binds the
   table name as a parameter and only samples tables that actually exist in the catalog,
   so a crafted "table name" cannot smuggle SQL.
4. Single statement only — multi-statement payloads (`SELECT 1; DROP TABLE x`) are rejected.
"""
import json

import sqlglot
from langchain_core.tools import tool
from sqlglot import exp

from db.connection import read_only_connection, write_connection

# Statement AST types that only read. Allowlist, not denylist: anything sqlglot cannot
# positively identify as a query is refused rather than assumed safe.
_READ_EXPRESSIONS = (
    exp.Select,  # includes CTE-wrapped SELECTs and DuckDB's FROM-first syntax
    exp.SetOperation,  # UNION / INTERSECT / EXCEPT
    exp.Describe,
    exp.Show,
    exp.Pivot,
    exp.Summarize,
    exp.Values,
)

# Statement AST types that mutate data or schema — the only statements duckdb_execute runs.
_WRITE_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Merge,
)

_UNSUPPORTED = (
    "statement type not allowed. Only queries (SELECT, DESCRIBE, SHOW, ...) and data/schema "
    "changes (INSERT, UPDATE, DELETE, CREATE, ...) are supported — not COPY, ATTACH, INSTALL, "
    "SET, PRAGMA or similar."
)


def _read_conn():
    """Read-only connection — the hard enforcement layer for query tools."""
    return read_only_connection()


def _write_conn():
    return write_connection()


def classify_sql(query: str) -> str:
    """Classify a SQL string as 'read', 'write', 'unsupported', 'multi', 'empty', or
    'invalid: <err>'.

    Uses sqlglot's AST rather than keyword matching, so CTE-wrapped writes and other
    first-word bypasses are classified correctly.
    """
    if not query or not query.strip():
        return "empty"
    try:
        statements = [s for s in sqlglot.parse(query, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        return f"invalid: {e.errors[0]['description'] if e.errors else e}"
    if not statements:
        return "empty"
    if len(statements) > 1:
        return "multi"
    statement = statements[0]
    if isinstance(statement, _WRITE_EXPRESSIONS):
        return "write"
    if isinstance(statement, _READ_EXPRESSIONS):
        # Defensive: a query must not contain a mutation anywhere in its tree.
        return "write" if statement.find(*_WRITE_EXPRESSIONS) else "read"
    return "unsupported"


@tool
def duckdb_list_tables() -> str:
    """List all tables in the operational DuckDB database."""
    try:
        with _read_conn() as conn:
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
        with _read_conn() as conn:
            # Allowlist: only tables that actually exist may be sampled.
            existing = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
            for table in tables:
                if table not in existing:
                    output.append(f"Table '{table}': not found.")
                    continue
                try:
                    schema_rows = conn.execute(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = ? ORDER BY ordinal_position",
                        [table],
                    ).fetchall()
                    cols = "\n".join(f"  {col}: {dtype}" for col, dtype in schema_rows)
                    # Identifier is allowlisted above; quote it defensively anyway.
                    sample = conn.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
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
    """Validate a SQL query before execution. Always call this before duckdb_execute.
    Returns 'OK — read query' for reads, 'OK — write query' for mutations, or an error."""
    kind = classify_sql(query)
    if kind == "empty":
        return "INVALID — empty statement."
    if kind == "multi":
        return "INVALID — multiple statements are not allowed; send one statement at a time."
    if kind.startswith("invalid"):
        return f"INVALID — {kind[9:]}"
    if kind == "unsupported":
        return "INVALID — " + _UNSUPPORTED

    if kind == "read":
        # EXPLAIN on the read-only connection validates against the live catalog.
        try:
            with _read_conn() as conn:
                conn.execute(f"EXPLAIN {query}")
            return "OK — read query."
        except Exception as e:
            return f"INVALID — {e}"
    return "OK — write query."


@tool
def duckdb_query(query: str) -> str:
    """Execute a read-only SELECT query against the operational DuckDB database.
    Rejects mutation statements. Results capped at 100 rows."""
    kind = classify_sql(query)
    if kind == "write":
        return (
            "[duckdb_query] Rejected — this statement mutates data. "
            "Use duckdb_execute (requires human approval) for writes."
        )
    if kind == "multi":
        return "[duckdb_query] Rejected — send one statement at a time."
    if kind == "unsupported":
        return "[duckdb_query] Rejected — " + _UNSUPPORTED
    if kind == "empty" or kind.startswith("invalid"):
        return f"[duckdb_query] Rejected — {kind}."
    try:
        # read_only=True: even if classification were wrong, the DB refuses writes.
        with _read_conn() as conn:
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
    do not call this without first calling duckdb_query_checker. Rejects read statements."""
    kind = classify_sql(statement)
    if kind == "read":
        return (
            "[duckdb_execute] Rejected — only mutation statements allowed here. "
            "Use duckdb_query for reads."
        )
    if kind == "multi":
        return "[duckdb_execute] Rejected — send one statement at a time."
    if kind == "unsupported":
        return "[duckdb_execute] Rejected — " + _UNSUPPORTED
    if kind == "empty" or kind.startswith("invalid"):
        return f"[duckdb_execute] Rejected — {kind}."
    try:
        with _write_conn() as conn:
            conn.execute(statement)
        return "Statement executed successfully."
    except Exception as e:
        return f"[duckdb_execute] Error: {e}"
