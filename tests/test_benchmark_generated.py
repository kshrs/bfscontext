def test_token_estimator():
    """Test that estimate_tokens returns an integer greater than zero."""
    # Assuming estimate_tokens is a function imported from a module
    result = estimate_tokens("sample text")
    assert isinstance(result, int)
    assert result > 0
