"""Check that SQL written by the LLM is a single, read-only query."""

import re

FORBIDDEN = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "ATTACH",
    "DETACH",
    "COPY",
    "EXPORT",
    "IMPORT",
    "INSTALL",
    "LOAD",
    "PRAGMA",
    "CALL",
    "TRUNCATE",
]


class UnsafeSQLError(ValueError):
    """Raised when a query is not allowed to run."""


def strip_comments(sql):
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)


def validate_sql(sql):
    """Return a cleaned query, or raise UnsafeSQLError explaining the problem."""
    if not sql or not sql.strip():
        raise UnsafeSQLError("The query is empty.")
    cleaned = strip_comments(sql).strip().rstrip(";").strip()
    if ";" in cleaned:
        raise UnsafeSQLError("Only one SQL statement is allowed.")
    first_word = cleaned.split(None, 1)[0].upper()
    if first_word not in ("SELECT", "WITH"):
        raise UnsafeSQLError("Only SELECT queries are allowed.")
    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", cleaned, flags=re.IGNORECASE):
            raise UnsafeSQLError(f"The keyword {word} is not allowed.")
    return cleaned


def run_query(con, sql, max_rows=1000):
    """Validate, then run the query and return at most max_rows rows as Polars."""
    safe_sql = validate_sql(sql)
    return con.execute(f"SELECT * FROM ({safe_sql}) AS q LIMIT {int(max_rows)}").pl()
