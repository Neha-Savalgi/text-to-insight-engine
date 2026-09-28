"""A thin wrapper around the Claude API, plus a helper to read JSON replies."""

import json
from dataclasses import dataclass

MODELS = {
    "Claude Haiku 4.5 (cheapest)": "claude-haiku-4-5-20251001",
    "Claude Sonnet 5 (smarter)": "claude-sonnet-5",
}

# US dollars per million tokens: (input, output). Check the pricing page for updates.
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
}


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class ClaudeClient:
    """Sends one message to Claude and returns the text plus token counts."""

    def __init__(self, api_key, model="claude-haiku-4-5-20251001"):
        import anthropic  # imported here so tests can run without an API key

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, system, user, max_tokens=1024):
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text, response.usage.input_tokens, response.usage.output_tokens
        )


def parse_json_reply(text):
    """Pull the JSON object out of a reply, even if it is wrapped in ```json fences."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("The model did not return JSON.")
    return json.loads(text[start : end + 1])


def estimate_cost(model, input_tokens, output_tokens):
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
