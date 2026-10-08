import subprocess
from pathlib import Path
import pytest

from circuit_breaker import (
    GuardrailResult,
    STATUS_FAILED_ROLLEDBACK,
    STATUS_REPAIRED,
    STATUS_SUCCESS,
    STATUS_TRIPPED,
    clear_escalation_handlers,
    extract_code,
    register_escalation_handler,
    validate_and_safeguard,
)

GOOD = "def f(x):\n    return x + 1\n"
BAD = "def f(x:\n    return x +\n"


@pytest.fixture
def repo(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    g("init")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    g("config", "commit.gpgsign", "false")
    (tmp_path / "billing.py").write_text("ORIGINAL = 1\n")
    g("add", ".")
    g("commit", "-m", "init")
    return tmp_path


def test_clean_markdown_passes(repo):
    raw = f"Sure! Here you go:\n```python\n{GOOD}```\nHope it helps."
    r = validate_and_safeguard(raw, "billing.py", str(repo))
    assert r.status == STATUS_SUCCESS
    assert r.clean_code == GOOD
    assert not r.auto_fix_attempted
    assert r.syntax_valid
    assert not r.rolled_back
    assert r.error_message is None


def test_crlf_windows_markdown_passes(repo):
    raw = f"Here is the code:\r\n```python\r\n{GOOD}```\r\nDone."
    r = validate_and_safeguard(raw, "billing.py", str(repo))
    assert r.status == STATUS_SUCCESS
    assert r.clean_code == GOOD
    assert r.syntax_valid


def test_no_fence_fallback():
    assert extract_code(GOOD) == GOOD


def test_unclosed_fence():
    assert extract_code("```python\n" + GOOD) == GOOD


def test_four_backticks_fence():
    raw = f"````python\n{GOOD}````"
    assert extract_code(raw) == GOOD


def test_multiple_fences_chooses_target_language(repo):
    raw = (
        "Install via:\n"
        "```bash\n"
        "pip install requests\n"
        "```\n"
        "Then execute:\n"
        "```python\n"
        f"{GOOD}"
        "```\n"
    )
    extracted = extract_code(raw, "billing.py")
    assert extracted == GOOD


def test_conversational_filler_without_fences(repo):
    raw = f"Sure! Here is the requested script:\n{GOOD}\nLet me know if you need any adjustments!"
    r = validate_and_safeguard(raw, "billing.py", str(repo))
    assert r.status == STATUS_SUCCESS
    assert r.clean_code == GOOD
    assert r.syntax_valid


def test_repair_succeeds(repo):
    calls = []

    def fixer(code, err):
        calls.append(err)
        return f"```python\n{GOOD}```"

    r = validate_and_safeguard(f"```python\n{BAD}```", "billing.py", str(repo), fixer)
    assert r.status == STATUS_REPAIRED
    assert r.auto_fix_attempted
    assert len(calls) == 1
    assert r.clean_code == GOOD
    assert r.syntax_valid
    assert not r.rolled_back


def test_trip_rolls_back_tracked(repo):
    f = repo / "billing.py"
    f.write_text("DIRTY = (\n")
    calls = []

    def fixer(code, err):
        calls.append(1)
        return BAD

    r = validate_and_safeguard(BAD, "billing.py", str(repo), fixer)
    # Status satisfies both "CIRCUIT_BREAKER_TRIPPED" and "FAILED_ROLLEDBACK"
    assert r.status == "CIRCUIT_BREAKER_TRIPPED"
    assert r.status == "FAILED_ROLLEDBACK"
    assert r.status == STATUS_TRIPPED
    assert r.status == STATUS_FAILED_ROLLEDBACK
    assert r.rolled_back
    assert len(calls) == 1  # Exactly ONE strike, prevents denial-of-wallet
    assert f.read_text() == "ORIGINAL = 1\n"  # Tracked file restored


def test_trip_removes_untracked(repo):
    f = repo / "test_new.py"
    f.write_text(BAD)
    r = validate_and_safeguard(BAD, "test_new.py", str(repo), None)
    assert r.rolled_back and not f.exists()
    assert r.clean_code == ""
    assert not r.syntax_valid
    assert not r.auto_fix_attempted


def test_dict_and_dataclass_access(repo):
    r = validate_and_safeguard(GOOD, "billing.py", str(repo))
    # Dataclass attribute access
    assert r.status == "SUCCESS"
    assert r.clean_code == GOOD
    # Dict access
    assert r["status"] == "SUCCESS"
    assert r["clean_code"] == GOOD
    assert r.get("status") == "SUCCESS"
    assert "status" in r
    d = r.to_dict()
    assert isinstance(d, dict)
    assert d["status"] == "SUCCESS"


def test_fixer_exception_counts_as_strike(repo):
    calls = []

    def failing_fixer(code, err):
        calls.append(1)
        raise RuntimeError("LLM rate limit or connection error")

    r = validate_and_safeguard(BAD, "billing.py", str(repo), failing_fixer)
    assert r.status == STATUS_TRIPPED
    assert r.auto_fix_attempted
    assert len(calls) == 1
    assert "Fixer call failed: RuntimeError" in (r.error_message or "")


def test_escalation_handler_triggered(repo):
    alerts = []
    clear_escalation_handlers()
    register_escalation_handler(lambda res: alerts.append(res))

    try:
        r = validate_and_safeguard(BAD, "billing.py", str(repo), None)
        assert r.status == STATUS_TRIPPED
        assert len(alerts) == 1
        assert alerts[0].target_file_path == "billing.py"
    finally:
        clear_escalation_handlers()