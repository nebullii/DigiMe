from dataclasses import dataclass


@dataclass(frozen=True)
class DraftRequest:
    platform: str
    profile: str
    incoming_message: str


@dataclass(frozen=True)
class DraftResponse:
    drafts: list[str]


class ReplyAgent:
    """Coordinates retrieval, prompt construction, and local model generation."""

    def draft(self, request: DraftRequest) -> DraftResponse:
        raise NotImplementedError("Reply generation will be implemented after ingestion and memory.")

