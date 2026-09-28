"""Load a CSV file into Polars, clean it, and put it inside DuckDB."""

import io
import re

import duckdb
import polars as pl

TABLE_NAME = "data"


def clean_column_names(columns):
    """Turn messy headers like 'Order Date ($)' into safe names like 'order_date'."""
    cleaned, seen = [], {}
    for col in columns:
        name = re.sub(r"[^0-9a-zA-Z]+", "_", str(col).strip()).strip("_").lower()
        if not name:
            name = "column"
        if name[0].isdigit():
            name = "col_" + name
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        cleaned.append(name)
    return cleaned


def load_csv(file_bytes):
    """Read raw CSV bytes into a Polars DataFrame with clean column names."""
    buffer = io.BytesIO(file_bytes)
    try:
        df = pl.read_csv(
            buffer,
            infer_schema_length=10_000,
            try_parse_dates=True,
            encoding="utf8-lossy",
        )
    except pl.exceptions.PolarsError:
        # Fallback: read every column as text so the upload never crashes.
        buffer.seek(0)
        df = pl.read_csv(buffer, infer_schema_length=0, encoding="utf8-lossy")
    if df.width == 0 or df.height == 0:
        raise ValueError("The CSV file looks empty.")
    return df.rename(dict(zip(df.columns, clean_column_names(df.columns))))


def create_connection(df):
    """Create an in-memory DuckDB database holding the DataFrame as table 'data'."""
    con = duckdb.connect(":memory:")
    con.register("uploaded_df", df.to_arrow())
    con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM uploaded_df")
    con.unregister("uploaded_df")
    # Safety: stop SQL from reading files on disk or the internet,
    # and stop anyone from switching that setting back on.
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con
