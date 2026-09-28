"""The brain of the app: question -> SQL -> result -> retry if needed -> narrative."""

import time
from dataclasses import dataclass, field
from typing import Optional

import polars as pl

from . import prompts
from .llm import parse_json_reply
from .schema import describe_table
from .sql_guard import run_query


@dataclass
class InsightResult:
    question: str
    sql: str = ""
    title: str = ""
    chart: dict = field(default_factory=dict)
    reasoning: str = ""
    data: Optional[pl.DataFrame] = None
    narrative: str = ""
    attempts: int = 0
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


class InsightEngine:
    def __init__(self, con, llm, max_retries=2, max_rows=1000):
        self.con = con
        self.llm = llm
        self.max_retries = max_retries
        self.max_rows = max_rows
        self.schema_text = describe_table(con)

    def _call(self, result, system, user, max_tokens):
        reply = self.llm.complete(system, user, max_tokens=max_tokens)
        result.input_tokens += reply.input_tokens
        result.output_tokens += reply.output_tokens
        return reply.text

    def generate_and_run_sql(self, question, result):
        """Ask Claude for SQL and run it. On failure, show Claude the error and retry."""
        previous_sql, previous_error = None, None
        for attempt in range(1, self.max_retries + 2):
            result.attempts = attempt
            user = prompts.build_sql_prompt(
                self.schema_text, question, previous_sql, previous_error
            )
            text = self._call(result, prompts.SQL_SYSTEM_PROMPT, user, max_tokens=800)
            try:
                plan = parse_json_reply(text)
                result.sql = plan["sql"]
                result.title = plan.get("title", "")
                result.chart = plan.get("chart") or {}
                result.reasoning = plan.get("reasoning", "")
                result.data = run_query(self.con, result.sql, self.max_rows)
                result.error = None
                return
            except Exception as exc:  # bad JSON, unsafe SQL, or a DuckDB error
                previous_sql = result.sql or text
                previous_error = f"{type(exc).__name__}: {exc}"
                result.error = previous_error
        result.data = None

    def write_narrative(self, question, result):
        preview = result.data.head(30).write_csv()
        user = prompts.build_narrative_prompt(
            question, result.sql, preview, result.data.height
        )
        text = self._call(result, prompts.NARRATIVE_SYSTEM_PROMPT, user, max_tokens=400)
        result.narrative = text.strip()

    def ask(self, question):
        start = time.perf_counter()
        result = InsightResult(question=question)
        self.generate_and_run_sql(question, result)
        if result.data is not None:
            self.write_narrative(question, result)
        result.seconds = round(time.perf_counter() - start, 2)
        return result
