"""Item 4 — PII / secret redaction."""
from backend.observability.redactor import redact_text, redact_value


def test_redacts_email():
    assert "REDACTED_EMAIL" in redact_text("contact ada@example.com today")


def test_redacts_aws_key():
    assert "REDACTED_AWS_KEY" in redact_text("AKIAIOSFODNN7EXAMPLE")


def test_redacts_jwt():
    s = "eyJabc.def.ghi"
    out = redact_text(s)
    assert "REDACTED_JWT" in out


def test_redacts_openai_style_token():
    assert "REDACTED_TOKEN" in redact_text("key=sk-abc123def456ghi789")


def test_redacts_github_pat():
    assert "REDACTED_TOKEN" in redact_text("ghp_1234567890abcdefghij")


def test_redacts_ipv4():
    assert "REDACTED_IP" in redact_text("server 10.0.0.1 is down")


def test_redacts_luhn_valid_credit_card():
    # A Luhn-valid 16-digit number.
    assert "REDACTED_CC" in redact_text("4111 1111 1111 1111")


def test_does_not_redact_luhn_invalid_long_digits():
    # 16-digit number that fails Luhn — must stay intact.
    text = "0123456789012345"
    out = redact_text(text)
    # It will get matched by the broad regex, but should not be CC-redacted.
    assert "REDACTED_CC" not in out


def test_redacts_recursively():
    payload = {"user": "ada@example.com", "items": ["sk-abcdef1234567890"]}
    out = redact_value(payload)
    assert out["user"] == "[REDACTED_EMAIL]"
    assert out["items"][0] == "[REDACTED_TOKEN]"


def test_performance_under_5ms_for_200_chars():
    import time

    s = ("sk-abcdefghij1234567890 " * 5) + ("ada@example.com " * 5)
    s = s[:200]
    t = time.perf_counter()
    for _ in range(50):
        redact_text(s)
    elapsed = (time.perf_counter() - t) / 50
    assert elapsed < 0.005  # 5 ms per call
