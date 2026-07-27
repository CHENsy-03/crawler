import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

PROTOCOL_VERSION = "1.0"



def new_task_id() -> str:
    return uuid.uuid4().hex[:12]


def new_message_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass(frozen=True, kw_only=True)
class MessageEnvelope:
    task_id: str
    message_id: str
    timestamp: str
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)




@dataclass(frozen=True, kw_only=True)
class SearchMessage(MessageEnvelope):
    type: Literal["search"] = "search"
    site: str
    keyword: str
    level: int
    max_pages: int


@dataclass(frozen=True, kw_only=True)
class URLMessage(MessageEnvelope):
    type: Literal["url"] = "url"
    url: str
    site: str
    keyword: str
    level: int
    title: str


@dataclass(frozen=True, kw_only=True)
class HTMLMessage(MessageEnvelope):
    type: Literal["html"] = "html"
    url: str
    site: str
    keyword: str
    level: int
    title: str
    html: str


@dataclass(frozen=True, kw_only=True)
class ResultMessage(MessageEnvelope):
    type: Literal["result"] = "result"
    site: str
    keyword: str
    level: int
    url: str
    title: str
    publish_date: str
    content: str
    summary: str
    score: int
    matched_keywords: list[str]


@dataclass(frozen=True, kw_only=True)
class SearchDoneMessage(MessageEnvelope):
    type: Literal["search_done"] = "search_done"
    site: str
    keyword: str
    url_count: int
    level: int


@dataclass(frozen=True, kw_only=True)
class ErrorMessage(MessageEnvelope):
    type: Literal["error"] = "error"
    stage: Literal["search", "download", "parse", "store"]
    site: str
    keyword: str
    level: int
    url: str
    error_code: str
    error: str
    retryable: bool
