"""Text-to-Insight Engine: upload a CSV, ask questions in plain English."""

import os
from pathlib import Path

import streamlit as st

from insight_engine.charts import build_figure, single_value
from insight_engine.llm import MODELS, ClaudeClient, estimate_cost
from insight_engine.loader import create_connection, load_csv
from insight_engine.pipeline import InsightEngine

SAMPLE_FILE = Path(__file__).parent / "sample_data" / "sales.csv"
EXAMPLE_QUESTIONS = [
    "What is the total revenue by region?",
    "How did monthly revenue change over time?",
    "Which 5 products sold the most units?",
    "Do discounts lead to more units per order?",
]

st.set_page_config(
    page_title="Text-to-Insight Engine", page_icon=":bar_chart:", layout="wide"
)


# ---------- helpers ----------
def get_secret(name, default=None):
    """Look for a setting in environment variables first, then in Streamlit secrets."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        return st.secrets[name]
    except Exception:
        return default


@st.cache_resource(show_spinner="Loading your data...", max_entries=5)
def prepare_data(file_bytes):
    """Runs once per file. Cached so re-runs of the page stay fast."""
    df = load_csv(file_bytes)
    return df, create_connection(df)


def show_result(result, model, key):
    """Draw one answer. 'key' must be unique so Streamlit can tell charts apart."""
    st.markdown(f"**{result.title or result.question}**")
    if result.error and result.data is None:
        st.error(
            f"I could not answer that after {result.attempts} tries. Last error: {result.error}"
        )
        return
    value = single_value(result.data)
    fig = build_figure(result.data, result.chart, result.title)
    if value is not None:
        if isinstance(value, float):
            value = f"{value:,.2f}"
        elif isinstance(value, int):
            value = f"{value:,}"
        st.metric(label=result.data.columns[0].replace("_", " ").title(), value=value)
    elif fig is not None:
        st.plotly_chart(fig, width="stretch", key=f"chart_{key}")
    else:
        st.dataframe(result.data, width="stretch")
    st.write(result.narrative)
    with st.expander("Show SQL, data, and cost"):
        st.code(result.sql, language="sql")
        st.caption(result.reasoning)
        st.dataframe(result.data, width="stretch")
        cost = estimate_cost(model, result.input_tokens, result.output_tokens)
        st.caption(
            f"Attempts: {result.attempts} | Tokens in/out: {result.input_tokens}/"
            f"{result.output_tokens} | Est. cost: ${cost:.4f} | Time: {result.seconds}s"
        )


# ---------- sidebar ----------
with st.sidebar:
    st.header("Settings")
    owner_key = get_secret("ANTHROPIC_API_KEY")
    user_key = st.text_input(
        "Your Anthropic API key (optional)",
        type="password",
        help="Leave empty to use the demo key. Your key is never stored.",
    )
    api_key = user_key or owner_key
    model_label = st.selectbox("Model", list(MODELS))
    model = MODELS[model_label]
    max_questions = int(get_secret("MAX_QUESTIONS_PER_SESSION", 15))
    st.caption("Built with DuckDB, Polars, Claude, and Streamlit.")

# ---------- main page ----------
st.title(":bar_chart: Text-to-Insight Engine")
st.write(
    "Upload any CSV, ask a question in plain English, and get a chart plus an explanation."
)

uploaded = st.file_uploader("Upload a CSV file", type=["csv"])
use_sample = st.toggle("Use the sample sales dataset", value=uploaded is None)

if uploaded is not None and not use_sample:
    file_bytes = uploaded.getvalue()
elif use_sample and SAMPLE_FILE.exists():
    file_bytes = SAMPLE_FILE.read_bytes()
else:
    st.info("Upload a CSV or switch on the sample dataset to begin.")
    st.stop()

try:
    df, con = prepare_data(file_bytes)
except Exception as exc:
    st.error(f"Could not read that file: {exc}")
    st.stop()

with st.expander(f"Preview data ({df.height:,} rows, {df.width} columns)"):
    st.dataframe(df.head(50), width="stretch")

if not api_key:
    st.warning(
        "Add an API key in the sidebar (or in Streamlit secrets) to ask questions."
    )
    st.stop()

st.session_state.setdefault("history", [])
st.session_state.setdefault("questions_used", 0)

# Clear old answers when a different file is loaded.
file_id = hash(file_bytes)
if st.session_state.get("file_id") != file_id:
    st.session_state.file_id = file_id
    st.session_state.history = []

cols = st.columns(len(EXAMPLE_QUESTIONS))
clicked = None
for col, example in zip(cols, EXAMPLE_QUESTIONS):
    if col.button(example, width="stretch"):
        clicked = example

for i, past in enumerate(st.session_state.history):
    with st.chat_message("user"):
        st.write(past.question)
    with st.chat_message("assistant"):
        show_result(past, model, key=i)

question = st.chat_input("Ask a question about your data") or clicked
if question:
    using_demo_key = not user_key
    if using_demo_key and st.session_state.questions_used >= max_questions:
        st.warning(
            "Demo limit reached for this session. Add your own API key to keep going."
        )
        st.stop()
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # cursor() gives this request its own handle, which is safer when
            # several visitors use the app at the same time.
            engine = InsightEngine(con.cursor(), ClaudeClient(api_key, model))
            result = engine.ask(question)
        show_result(result, model, key=len(st.session_state.history))
    st.session_state.history.append(result)
    if using_demo_key:
        st.session_state.questions_used += 1
