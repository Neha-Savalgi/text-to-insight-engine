import os
from insight_engine.llm import ClaudeClient
from insight_engine.loader import create_connection, load_csv
from insight_engine.pipeline import InsightEngine
con = create_connection(load_csv(open("sample_data/sales.csv", "rb").read()))
engine = InsightEngine(con, ClaudeClient(os.environ["ANTHROPIC_API_KEY"]))
r = engine.ask("Which product category has the highest average order revenue?")
print(r.sql, "\n")
print(r.data, "\n")
print(r.narrative)
print("attempts:", r.attempts, "tokens:", r.input_tokens, r.output_tokens)