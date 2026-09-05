package store

import (
	"strings"
	"time"
)

// DataModelEntityV1 is the static entity contract for the 22-entity target model.
type DataModelEntityV1 struct {
	Name    string
	Table   string
	Primary string
}

var dataModelV1Entities = []DataModelEntityV1{
	{Name: "Admin", Table: "admin", Primary: "admin_id"},
	{Name: "Session", Table: "session", Primary: "session_id"},
	{Name: "APIToken", Table: "api_token", Primary: "token_id"},
	{Name: "IdempotencyRecord", Table: "idempotency_record", Primary: "idempotency_record_id"},
	{Name: "CrawlTask", Table: "crawl_task", Primary: "task_id"},
	{Name: "TaskAttempt", Table: "task_attempt", Primary: "attempt_id"},
	{Name: "TaskStage", Table: "task_stage", Primary: "stage_id"},
	{Name: "TaskEvent", Table: "task_event", Primary: "event_id"},
	{Name: "SearchCandidate", Table: "search_candidate", Primary: "candidate_id"},
	{Name: "FetchArtifact", Table: "fetch_artifact", Primary: "artifact_id"},
	{Name: "Article", Table: "article", Primary: "article_id"},
	{Name: "ArticleVersion", Table: "article_version", Primary: "article_version_id"},
	{Name: "TaskArticle", Table: "task_article", Primary: "task_article_id"},
	{Name: "ReviewDecision", Table: "review_decision", Primary: "decision_id"},
	{Name: "ExportJob", Table: "export_job", Primary: "job_id"},
	{Name: "Site", Table: "site", Primary: "site_code"},
	{Name: "Plugin", Table: "plugin", Primary: "plugin_id"},
	{Name: "OutboxEvent", Table: "outbox_event", Primary: "outbox_event_id"},
	{Name: "AuditLog", Table: "audit_log", Primary: "audit_log_id"},
	{Name: "DeadLetter", Table: "dead_letter", Primary: "dead_letter_id"},
	{Name: "Checkpoint", Table: "checkpoint", Primary: "checkpoint_id"},
	{Name: "GlobalBlockEntry", Table: "global_block_entry", Primary: "block_entry_id"},
}

// DataModelV1Entities returns immutable copies of the 22-entity contract.
func DataModelV1Entities() []DataModelEntityV1 {
	out := make([]DataModelEntityV1, len(dataModelV1Entities))
	copy(out, dataModelV1Entities)
	return out
}

// DataModelV1EntityNames returns the canonical 22 entity names in order.
func DataModelV1EntityNames() []string {
	entities := DataModelV1Entities()
	out := make([]string, len(entities))
	for i, entity := range entities {
		out[i] = entity.Name
	}
	return out
}

// DataModelV1TableNames returns the canonical 22 table names in order.
func DataModelV1TableNames() []string {
	entities := DataModelV1Entities()
	out := make([]string, len(entities))
	for i, entity := range entities {
		out[i] = entity.Table
	}
	return out
}

// DataModelV1PrimaryKeys returns the canonical primary key column per table.
func DataModelV1PrimaryKeys() map[string]string {
	entities := DataModelV1Entities()
	out := make(map[string]string, len(entities))
	for _, entity := range entities {
		out[entity.Table] = entity.Primary
	}
	return out
}

const canonicalULIDAlphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// IsCanonicalULIDV1 reports whether value is a canonical 26-character uppercase ULID.
func IsCanonicalULIDV1(value string) bool {
	if len(value) != 26 {
		return false
	}
	for _, r := range value {
		if !strings.ContainsRune(canonicalULIDAlphabet, r) {
			return false
		}
	}
	return true
}

// AdminV1 is the formal field model for the admin target table.
type AdminV1 struct {
	AdminID        string    `gorm:"column:admin_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"admin_id"`
	Username       string    `gorm:"column:username;type:varchar(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_admin_username" json:"username"`
	PasswordHash   string    `gorm:"column:password_hash;type:varchar(255);not null" json:"password_hash"`
	BootstrapState string    `gorm:"column:bootstrap_state;type:varchar(32);not null" json:"bootstrap_state"`
	Status         string    `gorm:"column:status;type:varchar(32);not null" json:"status"`
	CreatedAt      time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
	UpdatedAt      time.Time `gorm:"column:updated_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"updated_at"`
}

// TableName maps AdminV1 to admin.
func (AdminV1) TableName() string { return "admin" }

// SessionV1 is the formal field model for the session target table.
type SessionV1 struct {
	SessionID         string     `gorm:"column:session_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"session_id"`
	AdminID           string     `gorm:"column:admin_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_session_admin_id" json:"admin_id"`
	TokenHash         string     `gorm:"column:token_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_session_token_hash" json:"token_hash"`
	CSRFTokenHash     string     `gorm:"column:csrf_token_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"csrf_token_hash"`
	IdleExpiresAt     time.Time  `gorm:"column:idle_expires_at;type:datetime(6);not null" json:"idle_expires_at"`
	AbsoluteExpiresAt time.Time  `gorm:"column:absolute_expires_at;type:datetime(6);not null;index:idx_session_absolute_expires" json:"absolute_expires_at"`
	RevokedAt         *time.Time `gorm:"column:revoked_at;type:datetime(6)" json:"revoked_at"`
	CreatedAt         time.Time  `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps SessionV1 to session.
func (SessionV1) TableName() string { return "session" }

// APITokenV1 is the formal field model for the api_token target table.
type APITokenV1 struct {
	TokenID     string     `gorm:"column:token_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"token_id"`
	AdminID     string     `gorm:"column:admin_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_api_token_admin_id" json:"admin_id"`
	Name        string     `gorm:"column:name;type:varchar(128);not null" json:"name"`
	TokenHash   string     `gorm:"column:token_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_api_token_hash" json:"token_hash"`
	Scopes      string     `gorm:"column:scopes;type:json;not null" json:"scopes"`
	ExpiresAt   *time.Time `gorm:"column:expires_at;type:datetime(6);index:idx_api_token_expires_at" json:"expires_at"`
	RotatedFrom *string    `gorm:"column:rotated_from;type:char(26) CHARACTER SET ascii COLLATE ascii_bin" json:"rotated_from"`
	RevokedAt   *time.Time `gorm:"column:revoked_at;type:datetime(6)" json:"revoked_at"`
	CreatedAt   time.Time  `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps APITokenV1 to api_token.
func (APITokenV1) TableName() string { return "api_token" }

// IdempotencyRecordV1 is the formal field model for idempotency_record.
type IdempotencyRecordV1 struct {
	IdempotencyRecordID string    `gorm:"column:idempotency_record_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"idempotency_record_id"`
	ActorType           string    `gorm:"column:actor_type;type:varchar(32);not null" json:"actor_type"`
	ActorID             string    `gorm:"column:actor_id;type:varchar(128);not null" json:"actor_id"`
	Method              string    `gorm:"column:method;type:varchar(16);not null" json:"method"`
	Path                string    `gorm:"column:path;type:varchar(255);not null" json:"path"`
	IdempotencyKey      string    `gorm:"column:idempotency_key;type:varchar(128) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"idempotency_key"`
	RequestHash         string    `gorm:"column:request_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"request_hash"`
	Status              string    `gorm:"column:status;type:varchar(32);not null" json:"status"`
	ResourceID          *string   `gorm:"column:resource_id;type:varchar(128)" json:"resource_id"`
	ResponseRef         *string   `gorm:"column:response_ref;type:varchar(255)" json:"response_ref"`
	CreatedAt           time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
	ExpiresAt           time.Time `gorm:"column:expires_at;type:datetime(6);not null;index:idx_idempotency_record_expires" json:"expires_at"`
}

// TableName maps IdempotencyRecordV1 to idempotency_record.
func (IdempotencyRecordV1) TableName() string { return "idempotency_record" }

// SiteV1 is the formal field model for the site target table.
type SiteV1 struct {
	SiteCode           string    `gorm:"column:site_code;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"site_code"`
	SiteVersion        uint32    `gorm:"column:site_version;type:int unsigned;not null;default:1" json:"site_version"`
	Name               string    `gorm:"column:name;type:varchar(255);not null" json:"name"`
	Status             string    `gorm:"column:status;type:varchar(32);not null;index:idx_site_status" json:"status"`
	Capabilities       string    `gorm:"column:capabilities;type:json;not null" json:"capabilities"`
	PluginPolicy       string    `gorm:"column:plugin_policy;type:json;not null" json:"plugin_policy"`
	SecurityPolicyID   string    `gorm:"column:security_policy_id;type:varchar(128);not null" json:"security_policy_id"`
	AuthorizationBasis *string   `gorm:"column:authorization_basis;type:text" json:"authorization_basis"`
	RobotsHandling     string    `gorm:"column:robots_handling;type:varchar(64);not null" json:"robots_handling"`
	CreatedAt          time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
	UpdatedAt          time.Time `gorm:"column:updated_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"updated_at"`
}

// TableName maps SiteV1 to site.
func (SiteV1) TableName() string { return "site" }

// PluginV1 is the formal field model for the plugin target table.
type PluginV1 struct {
	PluginID      string     `gorm:"column:plugin_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"plugin_id"`
	PluginKey     string     `gorm:"column:plugin_key;type:varchar(128);not null;uniqueIndex:uq_plugin_key_version" json:"plugin_key"`
	PluginVersion string     `gorm:"column:plugin_version;type:varchar(32);not null;uniqueIndex:uq_plugin_key_version" json:"plugin_version"`
	PluginType    string     `gorm:"column:plugin_type;type:varchar(32);not null" json:"plugin_type"`
	Enabled       bool       `gorm:"column:enabled;type:tinyint(1);not null;default:1;index:idx_plugin_enabled" json:"enabled"`
	SchemaVersion string     `gorm:"column:schema_version;type:varchar(32);not null" json:"schema_version"`
	Status        string     `gorm:"column:status;type:varchar(32);not null" json:"status"`
	RegisteredAt  time.Time  `gorm:"column:registered_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"registered_at"`
	LastAuditedAt *time.Time `gorm:"column:last_audited_at;type:datetime(6)" json:"last_audited_at"`
}

// TableName maps PluginV1 to plugin.
func (PluginV1) TableName() string { return "plugin" }

// CrawlTaskV1 is the formal field model for the crawl_task target table.
type CrawlTaskV1 struct {
	TaskID        string     `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"task_id"`
	SiteCode      string     `gorm:"column:site_code;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_crawl_task_site" json:"site_code"`
	SiteVersion   uint32     `gorm:"column:site_version;type:int unsigned;not null" json:"site_version"`
	Keywords      string     `gorm:"column:keywords;type:json;not null" json:"keywords"`
	Mode          string     `gorm:"column:mode;type:varchar(32);not null" json:"mode"`
	Status        string     `gorm:"column:status;type:varchar(32);not null;index:idx_crawl_task_status_created" json:"status"`
	Stage         string     `gorm:"column:stage;type:varchar(32);not null" json:"stage"`
	Progress      uint32     `gorm:"column:progress;type:int unsigned;not null;default:0" json:"progress"`
	AttemptCount  uint32     `gorm:"column:attempt_count;type:int unsigned;not null;default:0" json:"attempt_count"`
	LimitSnapshot string     `gorm:"column:limit_snapshot;type:json;not null" json:"limit_snapshot"`
	PolicyID      string     `gorm:"column:policy_id;type:varchar(128);not null" json:"policy_id"`
	SearchPlanID  *string    `gorm:"column:search_plan_id;type:varchar(128)" json:"search_plan_id"`
	Outcome       *string    `gorm:"column:outcome;type:varchar(32)" json:"outcome"`
	RetryOfTaskID *string    `gorm:"column:retry_of_task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin" json:"retry_of_task_id"`
	CreatedAt     time.Time  `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
	ConfirmedAt   *time.Time `gorm:"column:confirmed_at;type:datetime(6)" json:"confirmed_at"`
	StartedAt     *time.Time `gorm:"column:started_at;type:datetime(6)" json:"started_at"`
	EndedAt       *time.Time `gorm:"column:ended_at;type:datetime(6)" json:"ended_at"`
	TimedOutAt    *time.Time `gorm:"column:timed_out_at;type:datetime(6)" json:"timed_out_at"`
}

// TableName maps CrawlTaskV1 to crawl_task.
func (CrawlTaskV1) TableName() string { return "crawl_task" }

// TaskAttemptV1 is the formal field model for the task_attempt target table.
type TaskAttemptV1 struct {
	AttemptID          string     `gorm:"column:attempt_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"attempt_id"`
	TaskID             string     `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_task_attempt_task_no" json:"task_id"`
	AttemptNo          uint32     `gorm:"column:attempt_no;type:int unsigned;not null;uniqueIndex:uq_task_attempt_task_no" json:"attempt_no"`
	Status             string     `gorm:"column:status;type:varchar(32);not null" json:"status"`
	LeaseTokenHash     *string    `gorm:"column:lease_token_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin" json:"lease_token_hash"`
	HeartbeatExpiresAt time.Time  `gorm:"column:heartbeat_expires_at;type:datetime(6);not null;index:idx_task_attempt_heartbeat" json:"heartbeat_expires_at"`
	CheckpointID       *string    `gorm:"column:checkpoint_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;index:idx_task_attempt_checkpoint" json:"checkpoint_id"`
	StartedAt          *time.Time `gorm:"column:started_at;type:datetime(6)" json:"started_at"`
	EndedAt            *time.Time `gorm:"column:ended_at;type:datetime(6)" json:"ended_at"`
}

// TableName maps TaskAttemptV1 to task_attempt.
func (TaskAttemptV1) TableName() string { return "task_attempt" }

// TaskStageV1 is the formal field model for the task_stage target table.
type TaskStageV1 struct {
	StageID   string     `gorm:"column:stage_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"stage_id"`
	TaskID    string     `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_task_stage_attempt" json:"task_id"`
	Stage     string     `gorm:"column:stage;type:varchar(32);not null;uniqueIndex:uq_task_stage_attempt" json:"stage"`
	AttemptNo uint32     `gorm:"column:attempt_no;type:int unsigned;not null;uniqueIndex:uq_task_stage_attempt" json:"attempt_no"`
	Status    string     `gorm:"column:status;type:varchar(32);not null" json:"status"`
	Expected  uint32     `gorm:"column:expected;type:int unsigned;not null;default:0" json:"expected"`
	Processed uint32     `gorm:"column:processed;type:int unsigned;not null;default:0" json:"processed"`
	Succeeded uint32     `gorm:"column:succeeded;type:int unsigned;not null;default:0" json:"succeeded"`
	Failed    uint32     `gorm:"column:failed;type:int unsigned;not null;default:0" json:"failed"`
	StartedAt *time.Time `gorm:"column:started_at;type:datetime(6)" json:"started_at"`
	EndedAt   *time.Time `gorm:"column:ended_at;type:datetime(6)" json:"ended_at"`
}

// TableName maps TaskStageV1 to task_stage.
func (TaskStageV1) TableName() string { return "task_stage" }

// TaskEventV1 is the formal field model for the task_event target table.
type TaskEventV1 struct {
	EventID      string    `gorm:"column:event_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"event_id"`
	TaskID       string    `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_task_event_task_event" json:"task_id"`
	EventType    string    `gorm:"column:event_type;type:varchar(64);not null" json:"event_type"`
	EventVersion string    `gorm:"column:event_version;type:varchar(16);not null" json:"event_version"`
	Payload      string    `gorm:"column:payload;type:json;not null" json:"payload"`
	CreatedAt    time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6);index:idx_task_event_created" json:"created_at"`
}

// TableName maps TaskEventV1 to task_event.
func (TaskEventV1) TableName() string { return "task_event" }

// SearchCandidateV1 is the formal field model for search_candidate.
type SearchCandidateV1 struct {
	CandidateID       string    `gorm:"column:candidate_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"candidate_id"`
	TaskID            string    `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_search_candidate_task_url" json:"task_id"`
	DiscoverySource   string    `gorm:"column:discovery_source;type:varchar(64);not null" json:"discovery_source"`
	NormalizedURL     string    `gorm:"column:normalized_url;type:varchar(2048);not null" json:"normalized_url"`
	NormalizedURLHash string    `gorm:"column:normalized_url_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_search_candidate_task_url" json:"normalized_url_hash"`
	Confidence        uint32    `gorm:"column:confidence;type:int unsigned;not null;default:0" json:"confidence"`
	Evidence          string    `gorm:"column:evidence;type:json;not null" json:"evidence"`
	Status            string    `gorm:"column:status;type:varchar(32);not null;index:idx_search_candidate_task_status" json:"status"`
	CreatedAt         time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps SearchCandidateV1 to search_candidate.
func (SearchCandidateV1) TableName() string { return "search_candidate" }

// FetchArtifactV1 is the formal field model for fetch_artifact.
type FetchArtifactV1 struct {
	ArtifactID     string    `gorm:"column:artifact_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"artifact_id"`
	CandidateID    *string   `gorm:"column:candidate_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;index:idx_fetch_artifact_candidate" json:"candidate_id"`
	StorageKey     string    `gorm:"column:storage_key;type:varchar(512);not null;uniqueIndex:uq_fetch_artifact_storage_key" json:"storage_key"`
	ContentHash    string    `gorm:"column:content_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"content_hash"`
	ContentType    string    `gorm:"column:content_type;type:varchar(128);not null" json:"content_type"`
	ByteSize       uint64    `gorm:"column:byte_size;type:bigint unsigned;not null" json:"byte_size"`
	RetentionClass string    `gorm:"column:retention_class;type:varchar(32);not null" json:"retention_class"`
	HoldStatus     string    `gorm:"column:hold_status;type:varchar(32);not null;default:NONE" json:"hold_status"`
	Checksum       string    `gorm:"column:checksum;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"checksum"`
	FetchedAt      time.Time `gorm:"column:fetched_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"fetched_at"`
}

// TableName maps FetchArtifactV1 to fetch_artifact.
func (FetchArtifactV1) TableName() string { return "fetch_artifact" }

// ArticleV1 is the formal field model for the article target table.
type ArticleV1 struct {
	ArticleID       string    `gorm:"column:article_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"article_id"`
	ArticleKey      string    `gorm:"column:article_key;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_article_article_key" json:"article_key"`
	IdentityURL     string    `gorm:"column:identity_url;type:varchar(2048);not null" json:"identity_url"`
	IdentityURLHash string    `gorm:"column:identity_url_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_article_identity_hash" json:"identity_url_hash"`
	CanonicalURL    *string   `gorm:"column:canonical_url;type:varchar(2048)" json:"canonical_url"`
	LatestVersionID *string   `gorm:"column:latest_version_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin" json:"latest_version_id"`
	CreatedAt       time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6);index:idx_article_created" json:"created_at"`
}

// TableName maps ArticleV1 to article.
func (ArticleV1) TableName() string { return "article" }

// ArticleVersionV1 is the formal field model for article_version.
type ArticleVersionV1 struct {
	ArticleVersionID  string    `gorm:"column:article_version_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"article_version_id"`
	ArticleID         string    `gorm:"column:article_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_article_version_article" json:"article_id"`
	VersionNo         uint32    `gorm:"column:version_no;type:int unsigned;not null;uniqueIndex:uq_article_version_no" json:"version_no"`
	ContentHash       string    `gorm:"column:content_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_article_version_content" json:"content_hash"`
	ContentStorageRef string    `gorm:"column:content_storage_ref;type:varchar(512);not null" json:"content_storage_ref"`
	RawEvidenceRef    *string   `gorm:"column:raw_evidence_ref;type:varchar(512)" json:"raw_evidence_ref"`
	ExtractionInfo    string    `gorm:"column:extraction_info;type:json;not null" json:"extraction_info"`
	CreatedAt         time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps ArticleVersionV1 to article_version.
func (ArticleVersionV1) TableName() string { return "article_version" }

// TaskArticleV1 is the formal field model for task_article.
type TaskArticleV1 struct {
	TaskArticleID    string    `gorm:"column:task_article_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"task_article_id"`
	TaskID           string    `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_task_article_task_hit" json:"task_id"`
	HitID            string    `gorm:"column:hit_id;type:varchar(128);not null;uniqueIndex:uq_task_article_task_hit" json:"hit_id"`
	CandidateID      *string   `gorm:"column:candidate_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin" json:"candidate_id"`
	ArticleID        *string   `gorm:"column:article_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin" json:"article_id"`
	ArticleVersionID *string   `gorm:"column:article_version_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;index:idx_task_article_article_version" json:"article_version_id"`
	OriginalQuery    string    `gorm:"column:original_query;type:varchar(500);not null" json:"original_query"`
	QueryTerm        string    `gorm:"column:query_term;type:varchar(500);not null" json:"query_term"`
	RelevanceScore   uint32    `gorm:"column:relevance_score;type:int unsigned;not null;default:0" json:"relevance_score"`
	QualityScore     uint32    `gorm:"column:quality_score;type:int unsigned;not null;default:0" json:"quality_score"`
	ReviewState      string    `gorm:"column:review_state;type:varchar(32);not null;default:NONE" json:"review_state"`
	ResultStatus     string    `gorm:"column:result_status;type:varchar(32);not null" json:"result_status"`
	PersistedAt      time.Time `gorm:"column:persisted_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"persisted_at"`
	MatchedEvidence  string    `gorm:"column:matched_evidence;type:json;not null" json:"matched_evidence"`
	CreatedAt        time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps TaskArticleV1 to task_article.
func (TaskArticleV1) TableName() string { return "task_article" }

// ReviewDecisionV1 is the formal field model for review_decision.
type ReviewDecisionV1 struct {
	DecisionID            string    `gorm:"column:decision_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"decision_id"`
	TaskArticleID         string    `gorm:"column:task_article_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"task_article_id"`
	ArticleVersionID      string    `gorm:"column:article_version_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"article_version_id"`
	AdminID               string    `gorm:"column:admin_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_review_decision_admin" json:"admin_id"`
	Decision              string    `gorm:"column:decision;type:varchar(32);not null" json:"decision"`
	Comment               *string   `gorm:"column:comment;type:text" json:"comment"`
	HoldArtifactID        string    `gorm:"column:hold_artifact_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_review_decision_hold_artifact" json:"hold_artifact_id"`
	HoldArtifactChecksum  string    `gorm:"column:hold_artifact_checksum;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"hold_artifact_checksum"`
	EvidenceSchemaVersion string    `gorm:"column:evidence_schema_version;type:varchar(32);not null" json:"evidence_schema_version"`
	EvidenceSnapshot      string    `gorm:"column:evidence_snapshot;type:json;not null" json:"evidence_snapshot"`
	CreatedAt             time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps ReviewDecisionV1 to review_decision.
func (ReviewDecisionV1) TableName() string { return "review_decision" }

// ExportJobV1 is the formal field model for export_job.
type ExportJobV1 struct {
	JobID          string     `gorm:"column:job_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"job_id"`
	TaskID         *string    `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;index:idx_export_job_task" json:"task_id"`
	Format         string     `gorm:"column:format;type:varchar(16);not null" json:"format"`
	Status         string     `gorm:"column:status;type:varchar(32);not null;index:idx_export_job_status_created" json:"status"`
	FilterSnapshot string     `gorm:"column:filter_snapshot;type:json;not null" json:"filter_snapshot"`
	FileStorageKey *string    `gorm:"column:file_storage_key;type:varchar(512)" json:"file_storage_key"`
	Manifest       *string    `gorm:"column:manifest;type:json" json:"manifest"`
	ExpiresAt      time.Time  `gorm:"column:expires_at;type:datetime(6);not null" json:"expires_at"`
	CreatedAt      time.Time  `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
	FinishedAt     *time.Time `gorm:"column:finished_at;type:datetime(6)" json:"finished_at"`
}

// TableName maps ExportJobV1 to export_job.
func (ExportJobV1) TableName() string { return "export_job" }

// OutboxEventV1 is the formal field model for outbox_event.
type OutboxEventV1 struct {
	OutboxEventID string     `gorm:"column:outbox_event_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"outbox_event_id"`
	AggregateType string     `gorm:"column:aggregate_type;type:varchar(64);not null" json:"aggregate_type"`
	AggregateID   string     `gorm:"column:aggregate_id;type:varchar(128) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"aggregate_id"`
	EventKey      string     `gorm:"column:event_key;type:varchar(128) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"event_key"`
	EventType     string     `gorm:"column:event_type;type:varchar(64);not null" json:"event_type"`
	EventVersion  string     `gorm:"column:event_version;type:varchar(16);not null" json:"event_version"`
	Payload       string     `gorm:"column:payload;type:json;not null" json:"payload"`
	Status        string     `gorm:"column:status;type:varchar(32);not null" json:"status"`
	AttemptCount  uint32     `gorm:"column:attempt_count;type:int unsigned;not null;default:0" json:"attempt_count"`
	NextAttemptAt time.Time  `gorm:"column:next_attempt_at;type:datetime(6);not null" json:"next_attempt_at"`
	DispatchedAt  *time.Time `gorm:"column:dispatched_at;type:datetime(6)" json:"dispatched_at"`
	CreatedAt     time.Time  `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps OutboxEventV1 to outbox_event.
func (OutboxEventV1) TableName() string { return "outbox_event" }

// AuditLogV1 is the formal field model for audit_log.
type AuditLogV1 struct {
	AuditLogID   uint64    `gorm:"column:audit_log_id;type:bigint unsigned;not null;autoIncrement;primaryKey" json:"audit_log_id"`
	ActorType    string    `gorm:"column:actor_type;type:varchar(32);not null" json:"actor_type"`
	ActorID      *string   `gorm:"column:actor_id;type:varchar(128)" json:"actor_id"`
	Action       string    `gorm:"column:action;type:varchar(128);not null" json:"action"`
	ResourceType string    `gorm:"column:resource_type;type:varchar(64);not null" json:"resource_type"`
	ResourceID   *string   `gorm:"column:resource_id;type:varchar(128)" json:"resource_id"`
	BeforeJSON   *string   `gorm:"column:before_json;type:json" json:"before_json"`
	AfterJSON    *string   `gorm:"column:after_json;type:json" json:"after_json"`
	RequestID    *string   `gorm:"column:request_id;type:varchar(128)" json:"request_id"`
	CreatedAt    time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps AuditLogV1 to audit_log.
func (AuditLogV1) TableName() string { return "audit_log" }

// DeadLetterV1 is the formal field model for dead_letter.
type DeadLetterV1 struct {
	DeadLetterID string    `gorm:"column:dead_letter_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"dead_letter_id"`
	Stream       string    `gorm:"column:stream;type:varchar(128);not null" json:"stream"`
	MessageID    string    `gorm:"column:message_id;type:varchar(128);not null" json:"message_id"`
	PayloadRef   *string   `gorm:"column:payload_ref;type:varchar(512)" json:"payload_ref"`
	ErrorCode    string    `gorm:"column:error_code;type:varchar(128);not null" json:"error_code"`
	AttemptCount uint32    `gorm:"column:attempt_count;type:int unsigned;not null;default:0" json:"attempt_count"`
	Status       string    `gorm:"column:status;type:varchar(32);not null" json:"status"`
	ReplayCount  uint32    `gorm:"column:replay_count;type:int unsigned;not null;default:0" json:"replay_count"`
	CreatedAt    time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

// TableName maps DeadLetterV1 to dead_letter.
func (DeadLetterV1) TableName() string { return "dead_letter" }

// CheckpointV1 is the formal field model for checkpoint.
type CheckpointV1 struct {
	CheckpointID  string    `gorm:"column:checkpoint_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"checkpoint_id"`
	TaskID        string    `gorm:"column:task_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_checkpoint_task_key" json:"task_id"`
	CheckpointKey string    `gorm:"column:checkpoint_key;type:varchar(128);not null;uniqueIndex:uq_checkpoint_task_key" json:"checkpoint_key"`
	Stage         string    `gorm:"column:stage;type:varchar(32);not null" json:"stage"`
	SchemaVersion string    `gorm:"column:schema_version;type:varchar(32);not null" json:"schema_version"`
	StateJSON     string    `gorm:"column:state_json;type:json;not null" json:"state_json"`
	Status        string    `gorm:"column:status;type:varchar(32);not null" json:"status"`
	CreatedAt     time.Time `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
	UpdatedAt     time.Time `gorm:"column:updated_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"updated_at"`
}

// TableName maps CheckpointV1 to checkpoint.
func (CheckpointV1) TableName() string { return "checkpoint" }

// GlobalBlockEntryV1 is the formal field model for global_block_entry.
type GlobalBlockEntryV1 struct {
	BlockEntryID      string     `gorm:"column:block_entry_id;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null;primaryKey" json:"block_entry_id"`
	MatchType         string     `gorm:"column:match_type;type:varchar(32) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"match_type"`
	PatternNormalized string     `gorm:"column:pattern_normalized;type:varchar(512) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"pattern_normalized"`
	ReasonCode        string     `gorm:"column:reason_code;type:varchar(32) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"reason_code"`
	ReasonSummary     string     `gorm:"column:reason_summary;type:varchar(255);not null" json:"reason_summary"`
	EvidenceRef       *string    `gorm:"column:evidence_ref;type:varchar(512)" json:"evidence_ref"`
	EffectiveAt       time.Time  `gorm:"column:effective_at;type:datetime(6);not null" json:"effective_at"`
	ExpiresAt         *time.Time `gorm:"column:expires_at;type:datetime(6)" json:"expires_at"`
	CreatedBy         string     `gorm:"column:created_by;type:char(26) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"created_by"`
	Status            string     `gorm:"column:status;type:varchar(32) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"status"`
	Version           uint32     `gorm:"column:version;type:int unsigned;not null;default:1" json:"version"`
	CreatedAt         time.Time  `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
	UpdatedAt         time.Time  `gorm:"column:updated_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"updated_at"`
	ActivePatternKey  *string    `gorm:"column:active_pattern_key;type:varchar(512) CHARACTER SET ascii COLLATE ascii_bin;->:false" json:"-"`
}

// TableName maps GlobalBlockEntryV1 to global_block_entry.
func (GlobalBlockEntryV1) TableName() string { return "global_block_entry" }

// DataModelV1FormalModels returns the 22 formal field models for tests and reflection.
func DataModelV1FormalModels() []any {
	return []any{
		&AdminV1{},
		&SessionV1{},
		&APITokenV1{},
		&IdempotencyRecordV1{},
		&CrawlTaskV1{},
		&TaskAttemptV1{},
		&TaskStageV1{},
		&TaskEventV1{},
		&SearchCandidateV1{},
		&FetchArtifactV1{},
		&ArticleV1{},
		&ArticleVersionV1{},
		&TaskArticleV1{},
		&ReviewDecisionV1{},
		&ExportJobV1{},
		&SiteV1{},
		&PluginV1{},
		&OutboxEventV1{},
		&AuditLogV1{},
		&DeadLetterV1{},
		&CheckpointV1{},
		&GlobalBlockEntryV1{},
	}
}
