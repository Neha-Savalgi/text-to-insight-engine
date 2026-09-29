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


def normalize(value):
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, bool):
        return int(value)
    return str(value) if value is not None else None


def rows_of(df_or_rows):
    rows = df_or_rows.rows() if hasattr(df_or_rows, "rows") else df_or_rows
    return [tuple(normalize(v) for v in row) for row in rows]


def strict_match(pred, gold):
    """Same rows (ignoring row order and column order)."""
    return Counter(tuple(sorted(map(str, r))) for r in pred) == Counter(
        tuple(sorted(map(str, r))) for r in gold
    )


def lenient_match(pred, gold):
    """Same number of rows, and every gold row's values appear inside one predicted row.
    This forgives extra helpful columns, like showing revenue next to the top region."""
    if len(pred) != len(gold):
        return False
    remaining = [Counter(map(str, r)) for r in pred]
    for g in gold:
        need = Counter(map(str, g))
        hit = next((i for i, p in enumerate(remaining) if not need - p), None)
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
