"""Measure how accurate the engine is. These numbers become your paper's results.

Run from the project folder:
    python -m eval.evaluate --models claude-haiku-4-5-20251001 claude-sonnet-5
"""

import argparse
import csv
import json
import os
import time
from collections import Counter
from pathlib import Path

from insight_engine.llm import ClaudeClient, estimate_cost
from insight_engine.loader import create_connection, load_csv
from insight_engine.pipeline import InsightEngine

ROOT = Path(__file__).resolve().parent.parent


TRUE_WORDS = {"true", "yes", "y", "1", "with discount", "discounted", "discount"}
FALSE_WORDS = {"false", "no", "n", "0", "no discount", "not discounted", "undiscounted"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]


def forms(value):
    """Return every reasonable written form of one cell value.

    Two cells count as equal when their form sets overlap. This lets the engine
    answer 2024-11-01 where the gold answer is 11, or 'With Discount' where the
    gold answer is true, without accepting an answer that is actually different.
    """
    if value is None:
        return {"none"}
    if isinstance(value, bool):
        return TRUE_WORDS if value else FALSE_WORDS
    if isinstance(value, (datetime.datetime, datetime.date)):
        d = value.date() if isinstance(value, datetime.datetime) else value
        return {d.isoformat(), f"{d.year}-{d.month:02d}", str(d.month), str(d.year),
                MONTHS[d.month - 1]}
    if isinstance(value, float):
        return {f"{round(value, 2):g}"}
    if isinstance(value, int):
        return {str(value)}
    text = str(value).strip().lower()
    out = {text}
    if text in TRUE_WORDS:
        out |= TRUE_WORDS
    if text in FALSE_WORDS:
        out |= FALSE_WORDS
    if text in MONTHS:
        out.add(str(MONTHS.index(text) + 1))
    try:                                   # numbers that arrived as text
        out.add(f"{round(float(text), 2):g}")
    except ValueError:
        pass
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        y, m, _ = text.split("-")
        out |= {f"{y}-{m}", str(int(m)), y, MONTHS[int(m) - 1]}
    return out


def canon(value):
    """One plain form of a value, used by the strict metric."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{round(value, 2):g}"
    return str(value).strip().lower()


def rows_of(df_or_rows):
    rows = df_or_rows.rows() if hasattr(df_or_rows, "rows") else df_or_rows
    return [tuple(row) for row in rows]


def row_contains(pred_row, gold_row):
    """True when every gold value matches a distinct value in the predicted row."""
    remaining = [forms(v) for v in pred_row]
    for gold_value in gold_row:
        wanted = forms(gold_value)
        hit = next((i for i, p in enumerate(remaining) if p & wanted), None)
        if hit is None:
            return False
        remaining.pop(hit)
    return True


def strict_match(pred, gold):
    """Same rows and same values, ignoring row order and column order."""
    def key(rows):
        return sorted(tuple(sorted(canon(v) for v in row)) for row in rows)

    return len(pred) == len(gold) and key(pred) == key(gold)


def lenient_match(pred, gold):
    """Rank-aware containment.

    The engine may add columns (revenue beside the winning region) and extra
    rows below the ones asked for, but every gold row must appear inside the
    first len(gold) predicted rows, so a model cannot pass by dumping the whole
    table in the wrong order.
    """
    if not gold:
        return not pred
    remaining = list(pred[: len(gold)])
    for gold_row in gold:
        hit = next((i for i, p in enumerate(remaining) if row_contains(p, gold_row)), None)
        if hit is None:
            return False
        remaining.pop(hit)
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["claude-haiku-4-5-20251001"])
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()

    df = load_csv((ROOT / "sample_data" / "sales.csv").read_bytes())
    con = create_connection(df)
    benchmark = json.loads((ROOT / "eval" / "benchmark.json").read_text())
    api_key = os.environ["ANTHROPIC_API_KEY"]

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"results_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    records = []

    for model in args.models:
        engine = InsightEngine(
            con.cursor(), ClaudeClient(api_key, model), max_retries=args.retries
        )
        for item in benchmark:
            gold = rows_of(con.execute(item["gold_sql"]).fetchall())
            result = engine.ask(item["question"])
            pred = rows_of(result.data) if result.data is not None else []
            record = {
                "model": model,
                "id": item["id"],
                "difficulty": item["difficulty"],
                "strict_correct": result.data is not None and strict_match(pred, gold),
                "lenient_correct": result.data is not None
                and lenient_match(pred, gold),
                "attempts": result.attempts,
                "failed": result.data is None,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": round(
                    estimate_cost(model, result.input_tokens, result.output_tokens), 5
                ),
                "seconds": result.seconds,
                "sql": result.sql.replace("\n", " "),
            }
            records.append(record)
            print(
                f"{model} {item['id']}: lenient={record['lenient_correct']} attempts={result.attempts}"
            )

    with out_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    print("\nSummary")
    for model in args.models:
        rows = [r for r in records if r["model"] == model]
        n = len(rows)
        print(
            f"{model}: strict {sum(r['strict_correct'] for r in rows)}/{n}, "
            f"lenient {sum(r['lenient_correct'] for r in rows)}/{n}, "
            f"needed a retry {sum(r['attempts'] > 1 for r in rows)}/{n}, "
            f"total cost ${sum(r['cost_usd'] for r in rows):.4f}"
        )
    print("Saved", out_file)


if __name__ == "__main__":
    main()
