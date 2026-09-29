# Text-to-Insight Engine

Upload any CSV, ask a question in plain English, and get back a chart, a short
written explanation, and the SQL that produced it.

**Live demo:** https://text-to-insight-engine-fuuaxzbyvqmu2qrzddkhji.streamlit.app/

![tests](https://github.com/Neha-Savalgi/text-to-insight-engine/actions/workflows/tests.yml/badge.svg)

## How it works
CSV upload
-> Polars reads and cleans the file (fixes messy column names, detects dates)
-> DuckDB loads it into an in-memory SQL table named "data"
-> a compact table description is built (columns, types, ranges, sample rows)
-> Claude turns question + description into DuckDB SQL and a chart choice (JSON)
-> a safety check allows only one read-only SELECT query, then DuckDB runs it
(if it fails, the error goes back to Claude to fix, up to 2 retries)
-> Plotly draws the chart, Claude writes a short narrative from the real result


## Key design decisions

- **The CSV never goes to the LLM.** Only a compact table description is sent
  (about 400 tokens for the sample dataset), so cost stays near a fifth of a
  cent per question no matter how large the file is, and the raw rows never
  leave the app apart from five sample rows.
- **Self-correction loop.** When a query fails, the DuckDB error message is fed
  back to the model so it can fix its own mistake.
- **Defense in depth.** SQL is validated as a single read-only statement,
  DuckDB file and network access is disabled and locked, and results are capped
  at 1,000 rows.
- **Grounded narratives.** The explanation is written from the actual query
  result, and the prompt forbids inventing numbers.
- **Cost controls.** A per-session question limit on the demo key, plus the
  option for visitors to supply their own key.

## Evaluation

A 10-question benchmark (3 easy, 4 medium, 3 hard) with hand-written gold SQL
lives in `eval/benchmark.json`. Each question is scored by running the gold
query and comparing result sets.

- **Strict**: identical rows and values.
- **Lenient**: same row count, and every gold value appears in the engine's
  rows. Forgives helpful extra columns, such as showing revenue beside the
  winning region.

Run on 2026-09-29 against the 3,000-row sample sales dataset:

| Model | Strict | Lenient | Retries used | Cost for 10 questions |
|---|---|---|---|---|
| Claude Haiku 4.5 | 5/10 | 6/10 | 0/10 | $0.023 |
| Claude Sonnet 5 | 5/10 | 5/10 | 0/10 | $0.061 |

Lenient accuracy by difficulty:

| Model | Easy | Medium | Hard |
|---|---|---|---|
| Claude Haiku 4.5 | 3/3 | 3/4 | 0/3 |
| Claude Sonnet 5 | 3/3 | 2/4 | 0/3 |

### What these numbers actually say

Every generated query executed successfully on the first attempt, for both
models. No question consumed a retry. The misses are therefore not invalid SQL
but answers whose shape differs from the gold answer, for example returning a
month as `November` where the gold answer is `11`, or a share as `39.3` where
the gold answer is `0.393`. Manual review of the hard and medium misses is in
progress, and the automated metric will be revised to compare semantically
rather than literally.

Because no retries occurred, the retry ablation (`--retries 0`) cannot measure
the self-correction loop on this benchmark. The small difference it showed is
run-to-run variation. A harder benchmark, with more ambiguous column names and
multi-step questions, is needed to test that loop properly.

Sonnet 5 cost about 2.6 times more than Haiku 4.5 without scoring higher here,
which suggests the current bottleneck is question difficulty and metric design
rather than model capability.

Reproduce:

```bash
python -m eval.evaluate --models claude-haiku-4-5-20251001 claude-sonnet-5
```

## Run it yourself

```bash
git clone https://github.com/Neha-Savalgi/text-to-insight-engine.git
cd text-to-insight-engine
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add your API key
streamlit run app.py
```

Run the tests (no API key needed): `python -m pytest -q`

## Project structure
app.py Streamlit user interface
insight_engine/
loader.py CSV -> Polars -> DuckDB, column cleaning, safety settings
schema.py Compact table description for the LLM
prompts.py Every prompt in one place
llm.py Claude API wrapper, JSON parsing, cost estimate
sql_guard.py Read-only SQL validation and execution
pipeline.py Question -> SQL -> retry -> narrative
charts.py Plotly chart builder with fallbacks
tests/ 15 unit tests that use a fake LLM
eval/ Benchmark questions, evaluation script, saved results
sample_data/ Demo dataset and the script that generates it


## Tech stack

DuckDB, Polars, Claude API, Streamlit, Plotly, pytest, GitHub Actions

## Limitations and next steps

- The scoring metric is literal and penalizes correct answers that are
  formatted differently. Fixing this is the top priority.
- One table at a time. No joins across several uploaded files.
- Very wide tables (hundreds of columns) make the description long and costly.
- Benchmark is small (10 questions, one dataset). Expanding to 50 questions
  across three public datasets is in progress.
- Planned: follow-up questions with conversation memory, prompt caching to cut
  input cost, multi-file support.

## Author

Neha Savalgi | [LinkedIn](https://linkedin.com/in/neha-sanjay-savalgi) |
[GitHub](https://github.com/Neha-Savalgi)
