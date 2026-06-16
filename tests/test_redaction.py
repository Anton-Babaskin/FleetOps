from fleetops.security.redaction import redact


def test_redaction_patterns() -> None:
    aws_key = "AKIA" + "1234567890ABCDEF"
    text = "\n".join(
        [
            "Authorization: Bearer abc.def.ghi",
            "Bearer plain-token-value",
            "password=supersecret",
            "password: supersecret",
            "passwd=supersecret",
            "token=supersecret",
            "api_key=supersecret",
            "secret=supersecret",
            aws_key,
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payloadpayload.signaturesignature",
        ]
    )
    redacted = redact(text)
    assert "supersecret" not in redacted
    assert "plain-token-value" not in redacted
    assert aws_key not in redacted
    assert redacted.count("[REDACTED]") >= 9
