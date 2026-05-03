from digime.agent.proxy_prompt import build_proxy_draft_prompt
from digime.agent.proxy_reply import parse_proxy_draft_response


def test_build_proxy_draft_prompt_contains_message() -> None:
    prompt = build_proxy_draft_prompt(
        message="Can you review this today?",
        platform="slack",
        profile="work_slack",
    )

    assert "Can you review this today?" in prompt
    assert "Platform: slack" in prompt
    assert "Style profile: work_slack" in prompt


def test_parse_proxy_draft_response_extracts_json() -> None:
    package = parse_proxy_draft_response(
        """
        Here is the JSON:
        {
          "summary": "They are asking for a review today.",
          "risk_checks": {
            "makes_commitment": true,
            "missing_context": true,
            "sensitive": false,
            "reason": "The reply may commit to timing without details."
          },
          "drafts": [
            {"label": "short", "text": "Yep, I can take a look later today."}
          ]
        }
        """
    )

    assert package.summary == "They are asking for a review today."
    assert package.risk_checks.makes_commitment is True
    assert package.drafts[0].text == "Yep, I can take a look later today."

