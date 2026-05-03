from digime.agent.meeting import looks_like_meeting_request, parse_meeting_request


def test_looks_like_meeting_request() -> None:
    assert looks_like_meeting_request("Can you arrange a meeting on Monday 11 am?")
    assert looks_like_meeting_request("Please set up a zoom call tomorrow at 3pm")
    assert not looks_like_meeting_request("What is the current weather?")


def test_parse_google_meet_request_defaults_to_google_meet() -> None:
    request = parse_meeting_request("Arrange a meeting on Monday 11 am", "America/New_York")

    assert request.platform == "google_meet"
    assert request.start is not None
    assert request.start.hour == 11
    assert request.start.minute == 0
    assert request.duration_minutes == 30


def test_parse_zoom_request_respects_specified_platform() -> None:
    request = parse_meeting_request("Set up a Zoom meeting Tuesday 2pm", "America/New_York")

    assert request.platform == "zoom"

