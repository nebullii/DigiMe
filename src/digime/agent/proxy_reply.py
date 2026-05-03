from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from digime.agent.proxy_prompt import build_proxy_draft_prompt


class RiskChecks(BaseModel):
    makes_commitment: bool
    missing_context: bool
    sensitive: bool
    reason: str


class DraftOption(BaseModel):
    label: str
    text: str


class ProxyDraftPackage(BaseModel):
    summary: str
    risk_checks: RiskChecks
    drafts: list[DraftOption] = Field(min_length=1)


@dataclass(frozen=True)
class ProxyDraftRequest:
    message: str
    platform: str = "unknown"
    profile: str = "default"
    additional_context: str | None = None


class ProxyReplyAgent:
    def __init__(self, llm: Any) -> None:
        self.llm = llm

    def draft(self, request: ProxyDraftRequest) -> ProxyDraftPackage:
        prompt = build_proxy_draft_prompt(
            message=request.message,
            platform=request.platform,
            profile=request.profile,
            additional_context=request.additional_context,
        )
        raw_response = self.llm.generate(prompt)
        return parse_proxy_draft_response(raw_response)


def parse_proxy_draft_response(raw_response: str) -> ProxyDraftPackage:
    data = json.loads(_extract_json_object(raw_response))
    return ProxyDraftPackage.model_validate(data)


def _extract_json_object(raw_response: str) -> str:
    text = raw_response.strip()
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object.")
    return text[start : end + 1]
