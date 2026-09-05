"""DEV-002 canonical status, error and event enums.

This module intentionally has no import-time file or network side effects.
Values mirror tests/fixtures/status_error_event_dictionary_v1.json.
"""

from __future__ import annotations

from enum import Enum


def _make_enum(name: str, members: dict[str, str]) -> type[Enum]:
    return Enum(name, members, type=str)


class CrawlTaskStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    RECOVERING = "RECOVERING"
    CANCELLING = "CANCELLING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL_SUCCEEDED = "PARTIAL_SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class TaskAttemptStatus(str, Enum):
    RUNNING = "RUNNING"
    LOST = "LOST"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStageName(str, Enum):
    DISCOVERY = "DISCOVERY"
    FETCH = "FETCH"
    PARSE = "PARSE"
    SCORE = "SCORE"
    FILTER = "FILTER"
    DEDUP = "DEDUP"
    PERSIST = "PERSIST"


class TaskStageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SiteStatus(str, Enum):
    DRAFT = "DRAFT"
    ANALYZING = "ANALYZING"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    READY = "READY"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"
    MIGRATION_PENDING = "MIGRATION_PENDING"


class SearchPlanStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    ACTIVE = "active"
    EXPIRED = "expired"


class SearchCandidateStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    FETCHED = "FETCHED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


class FetchArtifactStatus(str, Enum):
    PENDING = "PENDING"
    SAVED = "SAVED"
    FAILED = "FAILED"


class ArtifactHoldStatus(str, Enum):
    NONE = "NONE"
    PROMOTING = "PROMOTING"
    READY = "READY"
    QUARANTINED = "QUARANTINED"


class ArticleVersionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class TaskArticleStatus(str, Enum):
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    IRRELEVANT = "irrelevant"
    EXTRACT_FAILED = "extract_failed"
    UNSUPPORTED_FORMAT = "unsupported_format"


class ReviewDecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ExportJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class OutboxEventStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    FAILED = "FAILED"
    DEAD = "DEAD"


class DeadLetterStatus(str, Enum):
    OPEN = "OPEN"
    REPLAYED = "REPLAYED"
    RESOLVED = "RESOLVED"
    DISCARDED = "DISCARDED"


class CheckpointStatus(str, Enum):
    ACTIVE = "ACTIVE"
    APPLIED = "APPLIED"
    SUPERSEDED = "SUPERSEDED"


class AdminStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IDLE_EXPIRED = "IDLE_EXPIRED"
    ABSOLUTE_EXPIRED = "ABSOLUTE_EXPIRED"
    REVOKED = "REVOKED"


class APITokenStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class GlobalBlockEntryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class CapacityStatus(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    DRAIN_ONLY = "DRAIN_ONLY"


class StreamWorkClass(str, Enum):
    ROOT = "ROOT"
    CONTINUATION = "CONTINUATION"
    TERMINAL = "TERMINAL"
    OPTIONAL = "OPTIONAL"


class ReadinessStatus(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"


class ReleaseStatus(str, Enum):
    RELEASE_BLOCKED = "RELEASE_BLOCKED"


STATUS_ENUMS = {
    "crawl_task": CrawlTaskStatus,
    "task_attempt": TaskAttemptStatus,
    "task_stage_name": TaskStageName,
    "task_stage": TaskStageStatus,
    "site": SiteStatus,
    "search_plan": SearchPlanStatus,
    "search_candidate": SearchCandidateStatus,
    "fetch_artifact": FetchArtifactStatus,
    "artifact_hold": ArtifactHoldStatus,
    "article_version": ArticleVersionStatus,
    "task_article": TaskArticleStatus,
    "review_decision": ReviewDecisionStatus,
    "export_job": ExportJobStatus,
    "outbox_event": OutboxEventStatus,
    "dead_letter": DeadLetterStatus,
    "checkpoint": CheckpointStatus,
    "admin": AdminStatus,
    "session": SessionStatus,
    "api_token": APITokenStatus,
    "global_block_entry": GlobalBlockEntryStatus,
    "capacity": CapacityStatus,
    "stream_work_class": StreamWorkClass,
    "readiness": ReadinessStatus,
    "release": ReleaseStatus,
}


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    CSRF_FAILED = "csrf_failed"
    STATE_CONFLICT = "state_conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    DEPENDENCY_NOT_READY = "dependency_not_ready"
    SITE_NOT_READY = "site_not_ready"
    SCOPE_EXPIRED = "scope_expired"
    OVER_LIMIT = "over_limit"
    TASK_LIMIT_EXCEEDED = "task_limit_exceeded"
    EVENT_HISTORY_EXPIRED = "event_history_expired"
    SECURITY_POLICY_REJECTED = "security_policy_rejected"
    SEARCH_FAILED = "search_failed"
    NO_EXECUTABLE_PLAN = "no_executable_plan"
    FETCH_FAILED = "fetch_failed"
    PARSE_FAILED = "parse_failed"
    UNSUPPORTED_FORMAT = "unsupported_format"
    EVIDENCE_MISSING = "evidence_missing"
    NOT_RETRYABLE = "not_retryable"
    EXPORT_EXPIRED = "export_expired"
    WORKER_LOST = "worker_lost"
    PARSER_MEMORY_LIMIT_EXCEEDED = "parser_memory_limit_exceeded"
    PARSER_TIMEOUT = "parser_timeout"
    PARSER_PROCESS_LOST = "parser_process_lost"
    PARSER_DEADLINE_EXCEEDED = "parser_deadline_exceeded"
    EVIDENCE_HOLD_UNAVAILABLE = "evidence_hold_unavailable"
    EVIDENCE_CHECKSUM_MISMATCH = "evidence_checksum_mismatch"
    GLOBAL_BLOCKED = "global_blocked"
    STREAM_DRAIN_ONLY = "stream_drain_only"
    STORAGE_CAPACITY_BLOCKED = "storage_capacity_blocked"
    EXPORT_TEMP_SPACE_EXHAUSTED = "export_temp_space_exhausted"
    JS_CSP_BLOCKED = "js_csp_blocked"
    JS_CORS_CRITICAL_RESOURCE_FAILED = "js_cors_critical_resource_failed"
    JS_CROSS_ORIGIN_IFRAME_UNSUPPORTED = "js_cross_origin_iframe_unsupported"
    JS_CONTENT_TIMEOUT = "js_content_timeout"
    INVALID_TARGET_URL = "invalid_target_url"
    INVALID_KEYWORD = "invalid_keyword"
    EMPTY_KEYWORDS = "empty_keywords"
    INVALID_INTEGER = "invalid_integer"
    INVALID_MESSAGE = "invalid_message"
    INVALID_JSON = "invalid_json"
    MISSING_PROTOCOL_VERSION = "missing_protocol_version"
    INVALID_TYPE = "invalid_type"
    UNKNOWN_FIELD = "unknown_field"
    UNKNOWN_PROTOCOL_VERSION = "unknown_protocol_version"
    INVALID_BOOLEAN = "invalid_boolean"
    INVALID_PATH = "invalid_path"
    INVALID_PAIRS = "invalid_pairs"
    INVALID_JSON_VALUE = "invalid_json_value"
    INVALID_JSON_TEMPLATE = "invalid_json_template"
    NO_RESULTS = "no_results"
    NO_CANDIDATE = "no_candidate"
    ANALYSIS_FAILED = "analysis_failed"
    PUBLISH_FAILURE = "publish_failure"
    ALREADY_INITIALIZED = "already_initialized"
    INVALID_CREDENTIALS = "invalid_credentials"
    TOKEN_LIMIT_EXCEEDED = "token_limit_exceeded"
    TASK_NOT_FOUND = "task_not_found"
    SITE_NOT_FOUND = "site_not_found"
    NOT_FOUND = "not_found"
    EXPORT_NOT_SUPPORTED = "export_not_supported"
    NOT_READY = "not_ready"
    ALREADY_TERMINAL = "already_terminal"


class EventType(str, Enum):
    TASK_STATUS_CHANGED = "task_status_changed"
    STAGE_PROGRESS = "stage_progress"
    WORKER_LOST = "worker_lost"
    RESULT_PERSISTED = "result_persisted"
    TASK_ERROR = "task_error"
    EXPORT_FINISHED = "export_finished"
    CHECKPOINT_UPDATED = "checkpoint_updated"
    SEARCH = "search"
    SEARCH_REQUESTED = "search_requested"
    URL = "url"
    HTML = "html"
    RESULT = "result"
    ERROR = "error"
    CACHE_INVALIDATED = "cache_invalidated"
    REVIEW_HOLD_READY = "review_hold_ready"
    REVIEW_HOLD_QUARANTINED = "review_hold_quarantined"
    GLOBAL_BLOCK_CHANGED = "global_block_changed"
    CAPACITY_NORMAL = "capacity_normal"
    CAPACITY_WARNING = "capacity_warning"
    CAPACITY_BLOCKED = "capacity_blocked"
    STREAM_DRAIN_ONLY = "stream_drain_only"
    GLOBAL_BLOCK_LEGAL_REQUEST_ACTIVATED = "global_block_legal_request_activated"


__all__ = [
    "CrawlTaskStatus",
    "TaskAttemptStatus",
    "TaskStageName",
    "TaskStageStatus",
    "SiteStatus",
    "SearchPlanStatus",
    "SearchCandidateStatus",
    "FetchArtifactStatus",
    "ArtifactHoldStatus",
    "ArticleVersionStatus",
    "TaskArticleStatus",
    "ReviewDecisionStatus",
    "ExportJobStatus",
    "OutboxEventStatus",
    "DeadLetterStatus",
    "CheckpointStatus",
    "AdminStatus",
    "SessionStatus",
    "APITokenStatus",
    "GlobalBlockEntryStatus",
    "CapacityStatus",
    "StreamWorkClass",
    "ReadinessStatus",
    "ReleaseStatus",
    "STATUS_ENUMS",
    "ErrorCode",
    "EventType",
]
