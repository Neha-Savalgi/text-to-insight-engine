"""Tests that run without an API key by using a fake LLM."""

import json

import polars as pl
import pytest

from insight_engine.charts import build_figure, single_value
from insight_engine.llm import LLMResponse, parse_json_reply
from insight_engine.loader import clean_column_names, create_connection, load_csv
from insight_engine.pipeline import InsightEngine
from insight_engine.schema import describe_table
from insight_engine.sql_guard import UnsafeSQLError, run_query, validate_sql

CSV = b"""Order Date,Region,Revenue ($)
2024-01-05,West,100.5
2024-01-20,East,200
2024-02-03,West,50
"""


@pytest.fixture
def con():
    return create_connection(load_csv(CSV))


class FakeLLM:
    """Pretends to be Claude: returns the replies we give it, in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, user, max_tokens=1024):
        self.calls.append(user)
        return LLMResponse(self.replies.pop(0), input_tokens=100, output_tokens=20)


def plan(sql, chart_type="bar"):
    return json.dumps(
        {
            "sql": sql,
            "title": "t",
            "chart": {"type": chart_type, "x": "region", "y": "total"},
            "reasoning": "r",
        }
    )


def test_clean_column_names():
    assert clean_column_names(["Order Date", "Revenue ($)", "2024", "a", "a"]) == [
        "order_date",
        "revenue",
        "col_2024",
        "a",
        "a_1",
    ]


def test_load_csv_parses_dates_and_numbers():
    df = load_csv(CSV)
    assert df.columns == ["order_date", "region", "revenue"]
    assert df.schema["order_date"] == pl.Date
    assert df.schema["revenue"] == pl.Float64


def test_describe_table_mentions_columns(con):
    text = describe_table(con)
    assert '"region"' in text and "Row count: 3" in text and "'West'" in text


@pytest.mark.parametrize(
    "bad",
    [
        "DROP TABLE data",
        "SELECT 1; DROP TABLE data",
        "INSERT INTO data VALUES (1)",
        "SELECT * FROM read_csv('secret.csv') -- sneaky\n; COPY data TO 'x.csv'",
        "",
    ],
)
def test_validate_sql_blocks_unsafe_queries(bad):
    with pytest.raises(UnsafeSQLError):
        validate_sql(bad)


def test_external_file_access_is_blocked(con):
    with pytest.raises(Exception):
        run_query(con, "SELECT * FROM read_csv('/etc/passwd')")


def test_run_query_works(con):
    df = run_query(
        con,
        'SELECT "region", SUM("revenue") AS total FROM data GROUP BY 1 ORDER BY 2 DESC;',
    )
    assert df.to_dicts()[0] == {"region": "East", "total": 200.0}


def test_parse_json_reply_handles_fences():
    assert parse_json_reply('```json\n{"sql": "SELECT 1"}\n```') == {"sql": "SELECT 1"}


def test_engine_happy_path(con):
    llm = FakeLLM(
        [
            plan('SELECT "region", SUM("revenue") AS total FROM data GROUP BY 1'),
            "West leads.",
        ]
    )
    result = InsightEngine(con, llm).ask("Revenue by region?")
    assert result.error is None and result.attempts == 1
    assert result.data.height == 2
    assert result.narrative == "West leads."
    assert result.input_tokens == 200


def test_engine_retries_after_a_bad_query(con):
    llm = FakeLLM(
        [
            plan('SELECT "wrong_column" FROM data'),
            plan('SELECT "region", SUM("revenue") AS total FROM data GROUP BY 1'),
            "Fixed answer.",
        ]
    )
    result = InsightEngine(con, llm).ask("Revenue by region?")
    assert result.attempts == 2 and result.error is None
    assert "Your previous query failed" in llm.calls[1]


def test_engine_gives_up_cleanly(con):
    llm = FakeLLM(["not json"] * 3)
    result = InsightEngine(con, llm, max_retries=2).ask("anything")
    assert result.data is None and result.error and result.attempts == 3


def test_charts(con):
    df = run_query(con, 'SELECT "region", SUM("revenue") AS total FROM data GROUP BY 1')
    assert build_figure(df, {"type": "bar", "x": "region", "y": "total"}) is not None
    assert (
        build_figure(df, {"type": "bar", "x": "nope", "y": "nope"}) is not None
    )  # falls back
    assert build_figure(df, {"type": "table"}) is None
    assert single_value(run_query(con, "SELECT COUNT(*) AS n FROM data")) == 3
