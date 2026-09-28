"""Describe a table in a compact text form that an LLM can read cheaply."""

from .loader import TABLE_NAME

LOW_CARDINALITY = 15


def describe_table(con, table=TABLE_NAME, sample_rows=5):
    """Return a short text summary: columns, types, ranges, sample values and rows."""
    row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    summary = con.execute(f"SUMMARIZE {table}").fetchall()
    # Each SUMMARIZE row starts with: name, type, min, max, approx_unique, ...
    # and ends with null_percentage.
    lines = [f"Table name: {table}", f"Row count: {row_count}", "", "Columns:"]
    for row in summary:
        name, col_type, col_min, col_max, approx_unique = row[:5]
        null_pct = row[-1]
        line = (
            f'- "{name}" ({col_type}): min={col_min}, max={col_max}, '
            f"~{approx_unique} distinct, {null_pct}% null"
        )
        if (
            col_type == "VARCHAR"
            and approx_unique is not None
            and approx_unique <= LOW_CARDINALITY
        ):
            values = con.execute(
                f'SELECT DISTINCT "{name}" FROM {table} '
                f'WHERE "{name}" IS NOT NULL ORDER BY 1 LIMIT {LOW_CARDINALITY}'
            ).fetchall()
            line += "; values: " + ", ".join(repr(v[0]) for v in values)
        lines.append(line)
    sample = con.execute(f"SELECT * FROM {table} LIMIT {sample_rows}").pl()
    lines += ["", f"First {sample_rows} rows (CSV):", sample.write_csv()]
    return "\n".join(lines)
