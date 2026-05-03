from digime.ingest.redaction import redact_text


def test_redact_email() -> None:
    assert redact_text("email me at person@example.com") == "email me at [REDACTED]"


def test_redact_card_like_number() -> None:
    assert redact_text("card 4242 4242 4242 4242") == "card [REDACTED]"

