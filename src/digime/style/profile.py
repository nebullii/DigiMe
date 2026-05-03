from pydantic import BaseModel


class StyleProfile(BaseModel):
    name: str
    platform: str
    tone: str
    rules: list[str]

