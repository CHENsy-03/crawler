package protocol

// StatusValue is a canonical status wire value.
type StatusValue string

// ErrorCode is a canonical stable error code.
type ErrorCode string

// EventType is a canonical event or message type.
type EventType string

// CrawlTask statuses.
const (
	CrawlTaskDraft               StatusValue = "DRAFT"
	CrawlTaskPendingConfirmation StatusValue = "PENDING_CONFIRMATION"
	CrawlTaskQueued              StatusValue = "QUEUED"
	CrawlTaskRunning             StatusValue = "RUNNING"
	CrawlTaskRetryWait           StatusValue = "RETRY_WAIT"
	CrawlTaskRecovering          StatusValue = "RECOVERING"
	CrawlTaskCancelling          StatusValue = "CANCELLING"
	CrawlTaskSucceeded           StatusValue = "SUCCEEDED"
	CrawlTaskPartialSucceeded    StatusValue = "PARTIAL_SUCCEEDED"
	CrawlTaskFailed              StatusValue = "FAILED"
	CrawlTaskCancelled           StatusValue = "CANCELLED"
	CrawlTaskTimedOut            StatusValue = "TIMED_OUT"
)

// TaskAttempt statuses.
const (
	TaskAttemptRunning   StatusValue = "RUNNING"
	TaskAttemptLost      StatusValue = "LOST"
	TaskAttemptSucceeded StatusValue = "SUCCEEDED"
	TaskAttemptFailed    StatusValue = "FAILED"
	TaskAttemptCancelled StatusValue = "CANCELLED"
)

// TaskStage names.
const (
	TaskStageDiscovery StatusValue = "DISCOVERY"
	TaskStageFetch     StatusValue = "FETCH"
	TaskStageParse     StatusValue = "PARSE"
	TaskStageScore     StatusValue = "SCORE"
	TaskStageFilter    StatusValue = "FILTER"
	TaskStageDedup     StatusValue = "DEDUP"
	TaskStagePersist   StatusValue = "PERSIST"
)

// TaskStage statuses.
const (
	TaskStageStatusPending   StatusValue = "PENDING"
	TaskStageStatusRunning   StatusValue = "RUNNING"
	TaskStageStatusSucceeded StatusValue = "SUCCEEDED"
	TaskStageStatusFailed    StatusValue = "FAILED"
)

// Site statuses.
const (
	SiteDraft             StatusValue = "DRAFT"
	SiteAnalyzing         StatusValue = "ANALYZING"
	SiteNeedsConfirmation StatusValue = "NEEDS_CONFIRMATION"
	SiteReady             StatusValue = "READY"
	SiteBlocked           StatusValue = "BLOCKED"
	SiteDisabled          StatusValue = "DISABLED"
	SiteMigrationPending  StatusValue = "MIGRATION_PENDING"
)

// SearchPlan statuses.
const (
	SearchPlanDraft   StatusValue = "draft"
	SearchPlanReady   StatusValue = "ready"
	SearchPlanActive  StatusValue = "active"
	SearchPlanExpired StatusValue = "expired"
)

// SearchCandidate statuses.
const (
	SearchCandidateDiscovered StatusValue = "DISCOVERED"
	SearchCandidateQueued     StatusValue = "QUEUED"
	SearchCandidateFetched    StatusValue = "FETCHED"
	SearchCandidateFailed     StatusValue = "FAILED"
	SearchCandidateDuplicate  StatusValue = "DUPLICATE"
)

// FetchArtifact statuses.
const (
	FetchArtifactPending StatusValue = "PENDING"
	FetchArtifactSaved   StatusValue = "SAVED"
	FetchArtifactFailed  StatusValue = "FAILED"
)

// Artifact hold statuses.
const (
	ArtifactHoldNone        StatusValue = "NONE"
	ArtifactHoldPromoting   StatusValue = "PROMOTING"
	ArtifactHoldReady       StatusValue = "READY"
	ArtifactHoldQuarantined StatusValue = "QUARANTINED"
)

// ArticleVersion statuses.
const (
	ArticleVersionActive     StatusValue = "ACTIVE"
	ArticleVersionSuperseded StatusValue = "SUPERSEDED"
)

// TaskArticle statuses.
const (
	TaskArticleAccepted          StatusValue = "accepted"
	TaskArticleReviewRequired    StatusValue = "review_required"
	TaskArticleIrrelevant        StatusValue = "irrelevant"
	TaskArticleExtractFailed     StatusValue = "extract_failed"
	TaskArticleUnsupportedFormat StatusValue = "unsupported_format"
)

// ReviewDecision statuses.
const (
	ReviewDecisionApproved    StatusValue = "APPROVED"
	ReviewDecisionRejected    StatusValue = "REJECTED"
	ReviewDecisionNeedsReview StatusValue = "NEEDS_REVIEW"
)

// ExportJob statuses.
const (
	ExportJobPending   StatusValue = "PENDING"
	ExportJobRunning   StatusValue = "RUNNING"
	ExportJobSucceeded StatusValue = "SUCCEEDED"
	ExportJobFailed    StatusValue = "FAILED"
	ExportJobExpired   StatusValue = "EXPIRED"
)

// OutboxEvent statuses.
const (
	OutboxEventPending    StatusValue = "PENDING"
	OutboxEventDispatched StatusValue = "DISPATCHED"
	OutboxEventFailed     StatusValue = "FAILED"
	OutboxEventDead       StatusValue = "DEAD"
)

// DeadLetter statuses.
const (
	DeadLetterOpen      StatusValue = "OPEN"
	DeadLetterReplayed  StatusValue = "REPLAYED"
	DeadLetterResolved  StatusValue = "RESOLVED"
	DeadLetterDiscarded StatusValue = "DISCARDED"
)

// Checkpoint statuses.
const (
	CheckpointActive     StatusValue = "ACTIVE"
	CheckpointApplied    StatusValue = "APPLIED"
	CheckpointSuperseded StatusValue = "SUPERSEDED"
)

// Admin statuses.
const (
	AdminInitializing StatusValue = "INITIALIZING"
	AdminActive       StatusValue = "ACTIVE"
	AdminDisabled     StatusValue = "DISABLED"
)

// Session statuses.
const (
	SessionActive          StatusValue = "ACTIVE"
	SessionIdleExpired     StatusValue = "IDLE_EXPIRED"
	SessionAbsoluteExpired StatusValue = "ABSOLUTE_EXPIRED"
	SessionRevoked         StatusValue = "REVOKED"
)

// APIToken statuses.
const (
	APITokenActive  StatusValue = "ACTIVE"
	APITokenExpired StatusValue = "EXPIRED"
	APITokenRevoked StatusValue = "REVOKED"
)

// GlobalBlockEntry statuses.
const (
	GlobalBlockEntryActive  StatusValue = "ACTIVE"
	GlobalBlockEntryExpired StatusValue = "EXPIRED"
	GlobalBlockEntryRevoked StatusValue = "REVOKED"
)

// Capacity statuses.
const (
	CapacityNormal    StatusValue = "NORMAL"
	CapacityWarning   StatusValue = "WARNING"
	CapacityBlocked   StatusValue = "BLOCKED"
	CapacityDrainOnly StatusValue = "DRAIN_ONLY"
)

// Stream work classes.
const (
	WorkClassRoot         StatusValue = "ROOT"
	WorkClassContinuation StatusValue = "CONTINUATION"
	WorkClassTerminal     StatusValue = "TERMINAL"
	WorkClassOptional     StatusValue = "OPTIONAL"
)

// Readiness statuses.
const (
	ReadinessReady    StatusValue = "READY"
	ReadinessNotReady StatusValue = "NOT_READY"
)

// Release status.
const (
	ReleaseBlocked StatusValue = "RELEASE_BLOCKED"
)

// StatusDomainValues returns immutable copies of values for a domain.
func StatusDomainValues(domain string) []string {
	switch domain {
	case "crawl_task":
		return copyStatuses(CrawlTaskDraft, CrawlTaskPendingConfirmation, CrawlTaskQueued, CrawlTaskRunning, CrawlTaskRetryWait, CrawlTaskRecovering, CrawlTaskCancelling, CrawlTaskSucceeded, CrawlTaskPartialSucceeded, CrawlTaskFailed, CrawlTaskCancelled, CrawlTaskTimedOut)
	case "task_attempt":
		return copyStatuses(TaskAttemptRunning, TaskAttemptLost, TaskAttemptSucceeded, TaskAttemptFailed, TaskAttemptCancelled)
	case "task_stage_name":
		return copyStatuses(TaskStageDiscovery, TaskStageFetch, TaskStageParse, TaskStageScore, TaskStageFilter, TaskStageDedup, TaskStagePersist)
	case "task_stage":
		return copyStatuses(TaskStageStatusPending, TaskStageStatusRunning, TaskStageStatusSucceeded, TaskStageStatusFailed)
	case "site":
		return copyStatuses(SiteDraft, SiteAnalyzing, SiteNeedsConfirmation, SiteReady, SiteBlocked, SiteDisabled, SiteMigrationPending)
	case "search_plan":
		return copyStatuses(SearchPlanDraft, SearchPlanReady, SearchPlanActive, SearchPlanExpired)
	case "search_candidate":
		return copyStatuses(SearchCandidateDiscovered, SearchCandidateQueued, SearchCandidateFetched, SearchCandidateFailed, SearchCandidateDuplicate)
	case "fetch_artifact":
		return copyStatuses(FetchArtifactPending, FetchArtifactSaved, FetchArtifactFailed)
	case "artifact_hold":
		return copyStatuses(ArtifactHoldNone, ArtifactHoldPromoting, ArtifactHoldReady, ArtifactHoldQuarantined)
	case "article_version":
		return copyStatuses(ArticleVersionActive, ArticleVersionSuperseded)
	case "task_article":
		return copyStatuses(TaskArticleAccepted, TaskArticleReviewRequired, TaskArticleIrrelevant, TaskArticleExtractFailed, TaskArticleUnsupportedFormat)
	case "review_decision":
		return copyStatuses(ReviewDecisionApproved, ReviewDecisionRejected, ReviewDecisionNeedsReview)
	case "export_job":
		return copyStatuses(ExportJobPending, ExportJobRunning, ExportJobSucceeded, ExportJobFailed, ExportJobExpired)
	case "outbox_event":
		return copyStatuses(OutboxEventPending, OutboxEventDispatched, OutboxEventFailed, OutboxEventDead)
	case "dead_letter":
		return copyStatuses(DeadLetterOpen, DeadLetterReplayed, DeadLetterResolved, DeadLetterDiscarded)
	case "checkpoint":
		return copyStatuses(CheckpointActive, CheckpointApplied, CheckpointSuperseded)
	case "admin":
		return copyStatuses(AdminInitializing, AdminActive, AdminDisabled)
	case "session":
		return copyStatuses(SessionActive, SessionIdleExpired, SessionAbsoluteExpired, SessionRevoked)
	case "api_token":
		return copyStatuses(APITokenActive, APITokenExpired, APITokenRevoked)
	case "global_block_entry":
		return copyStatuses(GlobalBlockEntryActive, GlobalBlockEntryExpired, GlobalBlockEntryRevoked)
	case "capacity":
		return copyStatuses(CapacityNormal, CapacityWarning, CapacityBlocked, CapacityDrainOnly)
	case "stream_work_class":
		return copyStatuses(WorkClassRoot, WorkClassContinuation, WorkClassTerminal, WorkClassOptional)
	case "readiness":
		return copyStatuses(ReadinessReady, ReadinessNotReady)
	case "release":
		return copyStatuses(ReleaseBlocked)
	default:
		return []string{}
	}
}

func copyStatuses(values ...StatusValue) []string {
	out := make([]string, len(values))
	for i, v := range values {
		out[i] = string(v)
	}
	return out
}

// Stable error codes.
const (
	ErrValidationError                ErrorCode = "validation_error"
	ErrUnauthorized                   ErrorCode = "unauthorized"
	ErrCSRFFailed                     ErrorCode = "csrf_failed"
	ErrStateConflict                  ErrorCode = "state_conflict"
	ErrIdempotencyConflict            ErrorCode = "idempotency_conflict"
	ErrDependencyNotReady             ErrorCode = "dependency_not_ready"
	ErrSiteNotReady                   ErrorCode = "site_not_ready"
	ErrScopeExpired                   ErrorCode = "scope_expired"
	ErrOverLimit                      ErrorCode = "over_limit"
	ErrTaskLimitExceeded              ErrorCode = "task_limit_exceeded"
	ErrEventHistoryExpired            ErrorCode = "event_history_expired"
	ErrSecurityPolicyRejected         ErrorCode = "security_policy_rejected"
	ErrSearchFailed                   ErrorCode = "search_failed"
	ErrNoExecutablePlan               ErrorCode = "no_executable_plan"
	ErrFetchFailed                    ErrorCode = "fetch_failed"
	ErrParseFailed                    ErrorCode = "parse_failed"
	ErrUnsupportedFormat              ErrorCode = "unsupported_format"
	ErrEvidenceMissing                ErrorCode = "evidence_missing"
	ErrNotRetryable                   ErrorCode = "not_retryable"
	ErrExportExpired                  ErrorCode = "export_expired"
	ErrWorkerLost                     ErrorCode = "worker_lost"
	ErrParserMemoryLimitExceeded      ErrorCode = "parser_memory_limit_exceeded"
	ErrParserTimeout                  ErrorCode = "parser_timeout"
	ErrParserProcessLost              ErrorCode = "parser_process_lost"
	ErrParserDeadlineExceeded         ErrorCode = "parser_deadline_exceeded"
	ErrEvidenceHoldUnavailable        ErrorCode = "evidence_hold_unavailable"
	ErrEvidenceChecksumMismatch       ErrorCode = "evidence_checksum_mismatch"
	ErrGlobalBlocked                  ErrorCode = "global_blocked"
	ErrStreamDrainOnly                ErrorCode = "stream_drain_only"
	ErrStorageCapacityBlocked         ErrorCode = "storage_capacity_blocked"
	ErrExportTempSpaceExhausted       ErrorCode = "export_temp_space_exhausted"
	ErrJSCSPBlocked                   ErrorCode = "js_csp_blocked"
	ErrJSCORSCriticalResourceFailed   ErrorCode = "js_cors_critical_resource_failed"
	ErrJSCrossOriginIframeUnsupported ErrorCode = "js_cross_origin_iframe_unsupported"
	ErrJSContentTimeout               ErrorCode = "js_content_timeout"
	ErrInvalidTargetURL               ErrorCode = "invalid_target_url"
	ErrInvalidKeyword                 ErrorCode = "invalid_keyword"
	ErrEmptyKeywords                  ErrorCode = "empty_keywords"
	ErrInvalidInteger                 ErrorCode = "invalid_integer"
	ErrInvalidMessage                 ErrorCode = "invalid_message"
	ErrInvalidJSON                    ErrorCode = "invalid_json"
	ErrMissingProtocolVersion         ErrorCode = "missing_protocol_version"
	ErrInvalidType                    ErrorCode = "invalid_type"
	ErrUnknownField                   ErrorCode = "unknown_field"
	ErrUnknownProtocolVersion         ErrorCode = "unknown_protocol_version"
	ErrInvalidBoolean                 ErrorCode = "invalid_boolean"
	ErrInvalidPath                    ErrorCode = "invalid_path"
	ErrInvalidPairs                   ErrorCode = "invalid_pairs"
	ErrInvalidJSONValue               ErrorCode = "invalid_json_value"
	ErrInvalidJSONTemplate            ErrorCode = "invalid_json_template"
	ErrNoResults                      ErrorCode = "no_results"
	ErrNoCandidate                    ErrorCode = "no_candidate"
	ErrAnalysisFailed                 ErrorCode = "analysis_failed"
	ErrPublishFailure                 ErrorCode = "publish_failure"
	ErrAlreadyInitialized             ErrorCode = "already_initialized"
	ErrInvalidCredentials             ErrorCode = "invalid_credentials"
	ErrTokenLimitExceeded             ErrorCode = "token_limit_exceeded"
	ErrTaskNotFound                   ErrorCode = "task_not_found"
	ErrSiteNotFound                   ErrorCode = "site_not_found"
	ErrNotFound                       ErrorCode = "not_found"
	ErrExportNotSupported             ErrorCode = "export_not_supported"
	ErrNotReady                       ErrorCode = "not_ready"
	ErrAlreadyTerminal                ErrorCode = "already_terminal"
)

// ErrorCodeValues returns an immutable copy of all stable error codes.
func ErrorCodeValues() []string {
	return copyErrors(
		ErrValidationError, ErrUnauthorized, ErrCSRFFailed, ErrStateConflict, ErrIdempotencyConflict,
		ErrDependencyNotReady, ErrSiteNotReady, ErrScopeExpired, ErrOverLimit, ErrSecurityPolicyRejected,
		ErrTaskLimitExceeded, ErrEventHistoryExpired,
		ErrSearchFailed, ErrNoExecutablePlan, ErrFetchFailed, ErrParseFailed, ErrUnsupportedFormat,
		ErrEvidenceMissing, ErrNotRetryable, ErrExportExpired, ErrWorkerLost, ErrParserMemoryLimitExceeded,
		ErrParserTimeout, ErrParserProcessLost, ErrParserDeadlineExceeded, ErrEvidenceHoldUnavailable,
		ErrEvidenceChecksumMismatch, ErrGlobalBlocked, ErrStreamDrainOnly, ErrStorageCapacityBlocked,
		ErrExportTempSpaceExhausted, ErrJSCSPBlocked, ErrJSCORSCriticalResourceFailed,
		ErrJSCrossOriginIframeUnsupported, ErrJSContentTimeout, ErrInvalidTargetURL, ErrInvalidKeyword,
		ErrEmptyKeywords, ErrInvalidInteger, ErrInvalidMessage, ErrInvalidJSON, ErrMissingProtocolVersion,
		ErrInvalidType, ErrUnknownField, ErrUnknownProtocolVersion, ErrInvalidBoolean, ErrInvalidPath,
		ErrInvalidPairs, ErrInvalidJSONValue, ErrInvalidJSONTemplate, ErrNoResults, ErrNoCandidate,
		ErrAnalysisFailed, ErrPublishFailure, ErrAlreadyInitialized, ErrInvalidCredentials,
		ErrTokenLimitExceeded, ErrTaskNotFound, ErrSiteNotFound, ErrNotFound, ErrExportNotSupported,
		ErrNotReady, ErrAlreadyTerminal,
	)
}

func copyErrors(values ...ErrorCode) []string {
	out := make([]string, len(values))
	for i, v := range values {
		out[i] = string(v)
	}
	return out
}

// Stable event and message types.
const (
	EventTaskStatusChanged                EventType = "task_status_changed"
	EventStageProgress                    EventType = "stage_progress"
	EventWorkerLost                       EventType = "worker_lost"
	EventResultPersisted                  EventType = "result_persisted"
	EventTaskError                        EventType = "task_error"
	EventExportFinished                   EventType = "export_finished"
	EventCheckpointUpdated                EventType = "checkpoint_updated"
	EventSearch                           EventType = "search"
	EventSearchRequested                  EventType = "search_requested"
	EventURL                              EventType = "url"
	EventHTML                             EventType = "html"
	EventResult                           EventType = "result"
	EventError                            EventType = "error"
	EventCacheInvalidated                 EventType = "cache_invalidated"
	EventReviewHoldReady                  EventType = "review_hold_ready"
	EventReviewHoldQuarantined            EventType = "review_hold_quarantined"
	EventGlobalBlockChanged               EventType = "global_block_changed"
	EventCapacityNormal                   EventType = "capacity_normal"
	EventCapacityWarning                  EventType = "capacity_warning"
	EventCapacityBlocked                  EventType = "capacity_blocked"
	EventStreamDrainOnly                  EventType = "stream_drain_only"
	EventGlobalBlockLegalRequestActivated EventType = "global_block_legal_request_activated"
)

// EventTypeValues returns an immutable copy of all event types.
func EventTypeValues() []string {
	return copyEvents(
		EventTaskStatusChanged, EventStageProgress, EventWorkerLost, EventResultPersisted, EventTaskError,
		EventExportFinished, EventCheckpointUpdated, EventSearch, EventSearchRequested, EventURL,
		EventHTML, EventResult, EventError, EventCacheInvalidated, EventReviewHoldReady,
		EventReviewHoldQuarantined, EventGlobalBlockChanged, EventCapacityNormal, EventCapacityWarning,
		EventCapacityBlocked, EventStreamDrainOnly, EventGlobalBlockLegalRequestActivated,
	)
}

func copyEvents(values ...EventType) []string {
	out := make([]string, len(values))
	for i, v := range values {
		out[i] = string(v)
	}
	return out
}
