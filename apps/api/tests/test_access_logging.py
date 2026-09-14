import logging

from acp_api.access_logging import (
    REDACTED_QUERY_VALUE,
    ArtifactTokenAccessLogFilter,
    install_access_log_redaction,
    redact_url_query_tokens,
)


def test_url_query_token_is_redacted_without_rewriting_other_parameters():
    target = "/artifacts/a/content?purpose=preview&token=v2.a.secret&range=1"

    redacted = redact_url_query_tokens(target)

    assert "v2.a.secret" not in redacted
    assert f"token={REDACTED_QUERY_VALUE}" in redacted
    assert "purpose=preview" in redacted
    assert "range=1" in redacted


def test_percent_encoded_token_name_cannot_bypass_redaction():
    target = "/artifacts/a/content?to%6ben=first&token=second&safe=visible"

    redacted = redact_url_query_tokens(target)

    assert "first" not in redacted
    assert "second" not in redacted
    assert redacted.count(REDACTED_QUERY_VALUE) == 2
    assert "safe=visible" in redacted


def test_uvicorn_access_record_is_redacted_before_formatting():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1:1234",
            "GET",
            "/artifacts/a/content?token=raw-secret",
            "1.1",
            200,
        ),
        None,
    )

    assert ArtifactTokenAccessLogFilter().filter(record) is True
    rendered = record.getMessage()

    assert "raw-secret" not in rendered
    assert REDACTED_QUERY_VALUE in rendered
    assert "/artifacts/a/content" in rendered


def test_filter_installation_is_idempotent():
    logger = logging.getLogger("acp.tests.uvicorn-access-redaction")
    logger.filters.clear()

    first = install_access_log_redaction(logger)
    second = install_access_log_redaction(logger)

    assert first is second
    assert sum(isinstance(item, ArtifactTokenAccessLogFilter) for item in logger.filters) == 1
    logger.removeFilter(first)
