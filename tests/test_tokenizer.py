"""
Tests for tokenizer and fallback estimation.
"""

from capsulemcp.tokenizer import TokenCounter


def test_token_counter_counting():
    counter = TokenCounter()
    text = "def hello():\n    return 'world'"
    tokens = counter.count_tokens(text)
    assert tokens > 0
    assert counter.count_tokens("") == 0


def test_calculate_metrics():
    counter = TokenCounter()
    raw = "def long_function():\n" + "    x = 1\n" * 100
    capsule = "def long_function():\n    x = 1"

    raw_t, cap_t, saved, pct, name = counter.calculate_metrics(raw, capsule)
    assert raw_t > cap_t
    assert saved == raw_t - cap_t
    assert 0.0 < pct < 100.0
    assert "tiktoken" in name or "fallback" in name
