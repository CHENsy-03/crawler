package store

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"crawler-platform/internal/protocol"
)

// ErrArticleResultConflict is returned when the same (task_id, hit_id) already
// exists with a different result_hash and must not be overwritten.
var ErrArticleResultConflict = errors.New("article_result_v2: task/hit result conflict")

// ArticleV2 represents one URL identity plus one content version in articles.
type ArticleV2 struct {
	ID               uint64     `gorm:"primaryKey;column:id" json:"id"`
	ArticleKey       string     `gorm:"column:article_key;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;uniqueIndex:uq_articles_article_key" json:"article_key"`
	IdentityURL      string     `gorm:"column:identity_url;type:varchar(2048);not null" json:"identity_url"`
	IdentityURLHash  string     `gorm:"column:identity_url_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_articles_identity_url_hash" json:"identity_url_hash"`
	CanonicalURL     string     `gorm:"column:canonical_url;type:varchar(2048);not null" json:"canonical_url"`
	FinalURL         string     `gorm:"column:final_url;type:varchar(2048);not null" json:"final_url"`
	Title            string     `gorm:"column:title;type:varchar(500);not null" json:"title"`
	PublishDate      *time.Time `gorm:"column:publish_date;type:date" json:"publish_date"`
	Source           string     `gorm:"column:source;type:varchar(500);not null" json:"source"`
	Summary          string     `gorm:"column:summary;type:text;not null" json:"summary"`
	Content          string     `gorm:"column:content;type:longtext;not null" json:"content"`
	ContentHash      string     `gorm:"column:content_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_articles_content_hash" json:"content_hash"`
	ExtractionMethod string     `gorm:"column:extraction_method;type:varchar(32);not null" json:"extraction_method"`
	FirstSeenAt      time.Time  `gorm:"column:first_seen_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"first_seen_at"`
	LastSeenAt       time.Time  `gorm:"column:last_seen_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"last_seen_at"`
}

func (ArticleV2) TableName() string { return "articles" }

// TaskArticleV2 represents one ArticleResultV2 delivery for one task hit.
type TaskArticleV2 struct {
	ID               uint64     `gorm:"primaryKey;column:id" json:"id"`
	ProtocolVersion  string     `gorm:"column:protocol_version;type:varchar(8);not null" json:"protocol_version"`
	TaskID           string     `gorm:"column:task_id;type:varchar(128);not null;uniqueIndex:uq_task_articles_task_hit;index:idx_task_articles_task_status,priority:1" json:"task_id"`
	HitID            string     `gorm:"column:hit_id;type:varchar(128);not null;uniqueIndex:uq_task_articles_task_hit" json:"hit_id"`
	PlanID           string     `gorm:"column:plan_id;type:varchar(128);not null;index:idx_task_articles_plan_id" json:"plan_id"`
	ArticleID        *uint64    `gorm:"column:article_id;type:bigint unsigned;index:idx_task_articles_article_id" json:"article_id"`
	ResultHash       string     `gorm:"column:result_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null" json:"result_hash"`
	ResultMessageID  string     `gorm:"column:result_message_id;type:varchar(128);not null" json:"result_message_id"`
	ResultTimestamp  time.Time  `gorm:"column:result_timestamp;type:datetime(6);not null" json:"result_timestamp"`
	OriginalQuery    string     `gorm:"column:original_query;type:varchar(500);not null" json:"original_query"`
	QueryTerm        string     `gorm:"column:query_term;type:varchar(500);not null" json:"query_term"`
	RequestedURL     string     `gorm:"column:requested_url;type:varchar(2048);not null" json:"requested_url"`
	FinalURL         string     `gorm:"column:final_url;type:varchar(2048);not null" json:"final_url"`
	CanonicalURL     string     `gorm:"column:canonical_url;type:varchar(2048);not null" json:"canonical_url"`
	Title            string     `gorm:"column:title;type:varchar(500);not null" json:"title"`
	PublishDate      *time.Time `gorm:"column:publish_date;type:date" json:"publish_date"`
	Source           string     `gorm:"column:source;type:varchar(500);not null" json:"source"`
	Summary          string     `gorm:"column:summary;type:text;not null" json:"summary"`
	ContentHash      string     `gorm:"column:content_hash;type:char(64) CHARACTER SET ascii COLLATE ascii_bin;not null;index:idx_task_articles_content_hash" json:"content_hash"`
	Score            uint       `gorm:"column:score;type:int unsigned;not null" json:"score"`
	MatchedEvidence  string     `gorm:"column:matched_evidence;type:json;not null" json:"matched_evidence"`
	Status           string     `gorm:"column:status;type:varchar(32);not null;index:idx_task_articles_task_status,priority:2" json:"status"`
	ExtractionMethod string     `gorm:"column:extraction_method;type:varchar(32);not null" json:"extraction_method"`
	CreatedAt        time.Time  `gorm:"column:created_at;type:datetime(6);not null;default:CURRENT_TIMESTAMP(6)" json:"created_at"`
}

func (TaskArticleV2) TableName() string { return "task_articles" }

// ArticleV2Records is the deterministic storage mapping for one ArticleResultV2.
type ArticleV2Records struct {
	Article             *ArticleV2
	TaskArticle         TaskArticleV2
	IdentityURL         string
	IdentityURLHash     string
	ArticleKey          string
	ResultHash          string
	ResultTimestamp     time.Time
	PublishDate         *time.Time
	MatchedEvidenceJSON string
}

type articleResultHashPayload struct {
	TaskID           string                     `json:"task_id"`
	HitID            string                     `json:"hit_id"`
	PlanID           string                     `json:"plan_id"`
	OriginalQuery    string                     `json:"original_query"`
	QueryTerm        string                     `json:"query_term"`
	RequestedURL     string                     `json:"requested_url"`
	FinalURL         string                     `json:"final_url"`
	CanonicalURL     string                     `json:"canonical_url"`
	Title            string                     `json:"title"`
	PublishDate      string                     `json:"publish_date"`
	Source           string                     `json:"source"`
	Summary          string                     `json:"summary"`
	ContentHash      string                     `json:"content_hash"`
	Score            int                        `json:"score"`
	MatchedEvidence  []protocol.MatchedEvidence `json:"matched_evidence"`
	Status           string                     `json:"status"`
	ExtractionMethod string                     `json:"extraction_method"`
}

func sha256Hex(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func identityURLFor(msg *protocol.ArticleResultV2) string {
	if msg.CanonicalURL != "" {
		return msg.CanonicalURL
	}
	return msg.FinalURL
}

func articleKeyFor(identityURL, contentHash string) string {
	return sha256Hex(identityURL + "\n" + contentHash)
}

func resultHashFor(msg *protocol.ArticleResultV2) (string, error) {
	evidence := msg.MatchedEvidence
	if evidence == nil {
		evidence = []protocol.MatchedEvidence{}
	}
	payload := articleResultHashPayload{
		TaskID:           msg.TaskID,
		HitID:            msg.HitID,
		PlanID:           msg.PlanID,
		OriginalQuery:    msg.OriginalQuery,
		QueryTerm:        msg.QueryTerm,
		RequestedURL:     msg.RequestedURL,
		FinalURL:         msg.FinalURL,
		CanonicalURL:     msg.CanonicalURL,
		Title:            msg.Title,
		PublishDate:      msg.PublishDate,
		Source:           msg.Source,
		Summary:          msg.Summary,
		ContentHash:      msg.ContentHash,
		Score:            msg.Score,
		MatchedEvidence:  evidence,
		Status:           msg.Status,
		ExtractionMethod: msg.ExtractionMethod,
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("marshal result_hash payload: %w", err)
	}
	return sha256Hex(string(data)), nil
}

func parsePublishDate(value string) (*time.Time, error) {
	if value == "" {
		return nil, nil
	}
	parsed, err := time.Parse("2006-01-02", value)
	if err != nil {
		return nil, fmt.Errorf("article_result publish_date %q is invalid: %w", value, err)
	}
	return &parsed, nil
}

func parseResultTimestamp(value string) (time.Time, error) {
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		return time.Time{}, fmt.Errorf("article_result timestamp %q is invalid: %w", value, err)
	}
	return parsed, nil
}

// BuildArticleResultV2Records validates a B1 ArticleResultV2 and deterministically
// maps it to articles/task_articles records. It never mutates the input message.
func BuildArticleResultV2Records(msg *protocol.ArticleResultV2) (*ArticleV2Records, error) {
	if msg == nil {
		return nil, fmt.Errorf("article_result_v2: message is nil")
	}
	if err := msg.Validate(); err != nil {
		return nil, fmt.Errorf("article_result_v2 validate: %w", err)
	}

	identityURL := identityURLFor(msg)
	identityURLHash := sha256Hex(identityURL)
	contentHash := msg.ContentHash
	articleKey := articleKeyFor(identityURL, contentHash)
	resultHash, err := resultHashFor(msg)
	if err != nil {
		return nil, err
	}
	publishDate, err := parsePublishDate(msg.PublishDate)
	if err != nil {
		return nil, err
	}
	resultTimestamp, err := parseResultTimestamp(msg.Timestamp)
	if err != nil {
		return nil, err
	}

	evidence := msg.MatchedEvidence
	if evidence == nil {
		evidence = []protocol.MatchedEvidence{}
	}
	evidenceJSON, err := json.Marshal(evidence)
	if err != nil {
		return nil, fmt.Errorf("marshal matched_evidence: %w", err)
	}

	records := &ArticleV2Records{
		IdentityURL:         identityURL,
		IdentityURLHash:     identityURLHash,
		ArticleKey:          articleKey,
		ResultHash:          resultHash,
		ResultTimestamp:     resultTimestamp,
		PublishDate:         publishDate,
		MatchedEvidenceJSON: string(evidenceJSON),
	}

	if msg.Content != "" {
		records.Article = &ArticleV2{
			ArticleKey:       articleKey,
			IdentityURL:      identityURL,
			IdentityURLHash:  identityURLHash,
			CanonicalURL:     msg.CanonicalURL,
			FinalURL:         msg.FinalURL,
			Title:            msg.Title,
			PublishDate:      publishDate,
			Source:           msg.Source,
			Summary:          msg.Summary,
			Content:          msg.Content,
			ContentHash:      msg.ContentHash,
			ExtractionMethod: msg.ExtractionMethod,
		}
	}

	records.TaskArticle = TaskArticleV2{
		ProtocolVersion:  msg.ProtocolVersion,
		TaskID:           msg.TaskID,
		HitID:            msg.HitID,
		PlanID:           msg.PlanID,
		ResultHash:       resultHash,
		ResultMessageID:  msg.MessageID,
		ResultTimestamp:  resultTimestamp,
		OriginalQuery:    msg.OriginalQuery,
		QueryTerm:        msg.QueryTerm,
		RequestedURL:     msg.RequestedURL,
		FinalURL:         msg.FinalURL,
		CanonicalURL:     msg.CanonicalURL,
		Title:            msg.Title,
		PublishDate:      publishDate,
		Source:           msg.Source,
		Summary:          msg.Summary,
		ContentHash:      msg.ContentHash,
		Score:            uint(msg.Score),
		MatchedEvidence:  records.MatchedEvidenceJSON,
		Status:           msg.Status,
		ExtractionMethod: msg.ExtractionMethod,
	}

	return records, nil
}
