package worker

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"crawler-platform/internal/protocol"
	"crawler-platform/internal/queue"
	"crawler-platform/internal/store"

	"github.com/redis/go-redis/v9"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

func requireB7WorkerE2E(t *testing.T) {
	t.Helper()
	if os.Getenv("TASK019B7_E2E") != "1" {
		t.Skip("TASK019B7_E2E worker integration test is disabled")
	}
	if os.Getenv("TASK019B7_MYSQL_DSN") == "" || os.Getenv("TASK019B7_REDIS_ADDR") == "" {
		t.Fatal("B7 DSN and Redis addr are required")
	}
}

func b7Hash(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func b7ArticleResult(taskID, hitID, status, content string) *protocol.ArticleResultV2 {
	contentHash := ""
	if content != "" {
		contentHash = b7Hash(content)
	}
	return &protocol.ArticleResultV2{
		ProtocolVersion: protocol.VersionV2,
		TaskID:          taskID,
		MessageID:       taskID + "-" + hitID + "-" + status,
		Timestamp:       "2026-08-13T10:00:00Z",
		Type:            protocol.TypeArticleResultV2,
		HitID:           hitID,
		PlanID:          "plan-b7",
		OriginalQuery:   "低空经济",
		QueryTerm:       "低空经济",
		RequestedURL:    "https://example.gov.cn/requested",
		FinalURL:        "https://example.gov.cn/final",
		CanonicalURL:    "https://example.gov.cn/canonical",
		Title:           "低空经济政策",
		PublishDate:     "2026-08-13",
		Source:          "example.gov.cn",
		Summary:         "摘要",
		Content:         content,
		ContentHash:     contentHash,
		Score:           5,
		MatchedEvidence: []protocol.MatchedEvidence{
			{Term: "低空经济", Origin: "original", Field: "title", Weight: 5},
			{Term: "低空经济", Origin: "original", Field: "content", Weight: 1},
		},
		Status:           status,
		ExtractionMethod: "density",
	}
}

func b7V1Result() *protocol.ResultMessage {
	return &protocol.ResultMessage{
		Envelope: protocol.Envelope{
			ProtocolVersion: protocol.Version,
			TaskID:          "b7-v1-task",
			MessageID:       "b7-v1-msg",
			Timestamp:       "2026-08-13T10:00:00Z",
		},
		Type:            "result",
		Site:            "example.gov.cn",
		Keyword:         "低空经济",
		Level:           1,
		URL:             "https://example.gov.cn/v1-final",
		Title:           "v1标题",
		PublishDate:     "2026-08-13",
		Content:         "v1正文内容",
		Score:           3,
		MatchedKeywords: []string{"低空经济"},
	}
}

func b7OpenGorm(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(mysql.Open(os.Getenv("TASK019B7_MYSQL_DSN")), &gorm.Config{})
	if err != nil {
		t.Fatalf("gorm open: %v", err)
	}
	sqlDB, err := db.DB()
	if err != nil {
		t.Fatalf("gorm sql db: %v", err)
	}
	t.Cleanup(func() { _ = sqlDB.Close() })
	return db
}

func b7WaitFor(t *testing.T, desc string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(30 * time.Second)
	for {
		if cond() {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("timeout waiting for %s", desc)
		}
		time.Sleep(250 * time.Millisecond)
	}
}

func b7Count(db *gorm.DB, table, where string, args ...any) int64 {
	var count int64
	if err := db.Table(table).Where(where, args...).Count(&count).Error; err != nil {
		return -1
	}
	return count
}

func b7PushBatch(t *testing.T, client *redis.Client, barrier []byte, messages ...[]byte) {
	t.Helper()
	_, err := client.TxPipelined(context.Background(), func(pipe redis.Pipeliner) error {
		if err := pipe.LPush(context.Background(), "crawler:result", barrier).Err(); err != nil {
			return err
		}
		for _, msg := range messages {
			if err := pipe.LPush(context.Background(), "crawler:result", msg).Err(); err != nil {
				return err
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("push batch: %v", err)
	}
}

func b7PushRaw(t *testing.T, client *redis.Client, data string) {
	t.Helper()
	if err := client.LPush(context.Background(), "crawler:result", data).Err(); err != nil {
		t.Fatalf("push raw: %v", err)
	}
}

func b7Marshal(t *testing.T, msg any) []byte {
	t.Helper()
	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return data
}

func TestTask019B7ResultConsumerE2E(t *testing.T) {
	requireB7WorkerE2E(t)

	ctx := context.Background()
	redisAddr := os.Getenv("TASK019B7_REDIS_ADDR")
	rq := queue.NewRedisQueue(redisAddr)
	redisClient := redis.NewClient(&redis.Options{Addr: redisAddr})
	defer redisClient.Close()

	myStore, err := store.NewMySQLStore(os.Getenv("TASK019B7_MYSQL_DSN"))
	if err != nil {
		t.Fatalf("NewMySQLStore: %v", err)
	}
	db := b7OpenGorm(t)

	p := NewPool(1, rq, myStore)
	p.StartResultConsumer()
	defer p.Stop()

	// Clean this isolated test database and the current result key so the
	// same isolated environment can safely run normal and race E2E passes.
	if err := redisClient.Del(ctx, "crawler:result").Err(); err != nil {
		t.Fatalf("reset result key: %v", err)
	}
	for _, statement := range []string{
		"DELETE FROM task_articles",
		"DELETE FROM articles",
		"DELETE FROM article",
		"DELETE FROM task",
	} {
		if err := db.Exec(statement).Error; err != nil {
			t.Fatalf("clean isolated db: %v", err)
		}
	}

	// Pre-create a sentinel legacy task that v2 must not touch.
	if err := db.Table("task").Create(map[string]any{
		"id": "b7-accept", "keyword": "kw", "site": "s", "status": "created", "article_count": 7,
	}).Error; err != nil {
		t.Fatalf("seed legacy task: %v", err)
	}

	// A. Accepted long content.
	longContent := strings.Repeat("低空经济正文", 1000)
	accepted := b7ArticleResult("b7-accept", "hit-accept", "accepted", longContent)
	barrier := b7ArticleResult("b7-barrier-1", "hit-barrier-1", "accepted", "barrier1")
	b7PushBatch(t, redisClient, b7Marshal(t, barrier), b7Marshal(t, accepted))
	b7WaitFor(t, "accepted persisted", func() bool {
		return b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-barrier-1", "hit-barrier-1") == 1
	})

	var articleRow struct {
		ID          uint64
		Content     string
		ContentHash string
	}
	if err := db.Table("articles").Where("content_hash = ?", accepted.ContentHash).Scan(&articleRow).Error; err != nil {
		t.Fatal(err)
	}
	if articleRow.Content != longContent || len(articleRow.Content) <= 5000 || articleRow.ContentHash != accepted.ContentHash {
		t.Fatalf("accepted article content mismatch len=%d", len(articleRow.Content))
	}
	var taskRow struct {
		ArticleID       *uint64
		ResultHash      string
		MatchedEvidence string
		Status          string
		RequestedURL    string
		FinalURL        string
		CanonicalURL    string
	}
	if err := db.Table("task_articles").Where("task_id = ? AND hit_id = ?", "b7-accept", "hit-accept").Scan(&taskRow).Error; err != nil {
		t.Fatal(err)
	}
	if taskRow.ArticleID == nil || *taskRow.ArticleID != articleRow.ID || taskRow.Status != "accepted" {
		t.Fatalf("task_articles linkage mismatch: %+v", taskRow)
	}
	var evidence []protocol.MatchedEvidence
	if err := json.Unmarshal([]byte(taskRow.MatchedEvidence), &evidence); err != nil {
		t.Fatal(err)
	}
	if len(evidence) != len(accepted.MatchedEvidence) || evidence[0].Term != accepted.MatchedEvidence[0].Term {
		t.Fatalf("evidence order mismatch: %+v", evidence)
	}

	// B. v2 must not touch legacy task.
	var legacyTask struct {
		Status       string
		ArticleCount int
	}
	if err := db.Table("task").Where("id = ?", "b7-accept").Scan(&legacyTask).Error; err != nil {
		t.Fatal(err)
	}
	if legacyTask.Status != "created" || legacyTask.ArticleCount != 7 {
		t.Fatalf("legacy task was polluted: %+v", legacyTask)
	}

	// C. Replay.
	replay := b7ArticleResult("b7-accept", "hit-accept", "accepted", longContent)
	replay.MessageID = "replayed-message-id"
	replay.Timestamp = "2026-08-14T00:00:00Z"
	barrier2 := b7ArticleResult("b7-barrier-2", "hit-barrier-2", "accepted", "barrier2")
	b7PushBatch(t, redisClient, b7Marshal(t, barrier2), b7Marshal(t, replay))
	b7WaitFor(t, "replay barrier", func() bool {
		return b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-barrier-2", "hit-barrier-2") == 1
	})
	if got := b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-accept", "hit-accept"); got != 1 {
		t.Fatalf("replay created duplicate task_articles: %d", got)
	}
	if got := b7Count(db, "articles", "content_hash = ?", accepted.ContentHash); got != 1 {
		t.Fatalf("replay created duplicate articles: %d", got)
	}

	// D. Conflict rollback.
	conflict := b7ArticleResult("b7-accept", "hit-accept", "irrelevant", "冲突正文")
	barrier3 := b7ArticleResult("b7-barrier-3", "hit-barrier-3", "accepted", "barrier3")
	b7PushBatch(t, redisClient, b7Marshal(t, barrier3), b7Marshal(t, conflict))
	b7WaitFor(t, "conflict barrier", func() bool {
		return b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-barrier-3", "hit-barrier-3") == 1
	})
	if got := b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-accept", "hit-accept"); got != 1 {
		t.Fatalf("conflict changed task_articles count: %d", got)
	}
	if got := b7Count(db, "articles", "content_hash = ?", conflict.ContentHash); got != 0 {
		t.Fatalf("conflict left orphan article: %d", got)
	}

	// E. Same URL, different hit_id.
	multi1 := b7ArticleResult("b7-multi", "hit-multi-1", "accepted", "multi正文1")
	multi2 := b7ArticleResult("b7-multi", "hit-multi-2", "accepted", "multi正文2")
	barrier4 := b7ArticleResult("b7-barrier-4", "hit-barrier-4", "accepted", "barrier4")
	b7PushBatch(t, redisClient, b7Marshal(t, barrier4), b7Marshal(t, multi1), b7Marshal(t, multi2))
	b7WaitFor(t, "multi-hit barrier", func() bool {
		return b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-barrier-4", "hit-barrier-4") == 1
	})
	if got := b7Count(db, "task_articles", "task_id = ? AND hit_id IN (?, ?)", "b7-multi", "hit-multi-1", "hit-multi-2"); got != 2 {
		t.Fatalf("same URL different hit_id count = %d", got)
	}

	// F. All statuses.
	statuses := []string{"accepted", "review_required", "irrelevant", "extract_failed", "unsupported_format"}
	msgs := make([][]byte, 0, len(statuses))
	for i, status := range statuses {
		msg := b7ArticleResult("b7-status-"+status, "hit-"+status, status, "状态正文"+status)
		if status == "extract_failed" || status == "unsupported_format" {
			msg = b7ArticleResult("b7-status-"+status, "hit-"+status, status, "")
		}
		msgs = append(msgs, b7Marshal(t, msg))
		_ = i
	}
	barrier5 := b7ArticleResult("b7-barrier-5", "hit-barrier-5", "accepted", "barrier5")
	b7PushBatch(t, redisClient, b7Marshal(t, barrier5), msgs...)
	b7WaitFor(t, "status barrier", func() bool {
		return b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-barrier-5", "hit-barrier-5") == 1
	})
	for _, status := range statuses {
		if got := b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-status-"+status, "hit-"+status); got != 1 {
			t.Fatalf("%s task_articles count = %d", status, got)
		}
	}
	var ef struct{ ArticleID *uint64 }
	if err := db.Table("task_articles").Select("article_id").Where("task_id = ?", "b7-status-extract_failed").Scan(&ef).Error; err != nil {
		t.Fatal(err)
	}
	if ef.ArticleID != nil {
		t.Fatalf("extract_failed article_id must be NULL")
	}

	// G. legacy/v1 coexists.
	if err := db.Table("task").Create(map[string]any{
		"id": "b7-v1-task", "keyword": "kw", "site": "s", "status": "created", "article_count": 0,
	}).Error; err != nil {
		t.Fatal(err)
	}
	if err := rq.PushResultMessage(b7V1Result()); err != nil {
		t.Fatalf("push v1: %v", err)
	}
	b7WaitFor(t, "v1 article persisted", func() bool { return b7Count(db, "article", "url = ?", "https://example.gov.cn/v1-final") == 1 })
	if got := b7Count(db, "articles", "final_url = ?", "https://example.gov.cn/v1-final"); got != 0 {
		t.Fatalf("v1 wrote to v2 articles: %d", got)
	}
	if got := b7Count(db, "task_articles", "task_id = ?", "b7-v1-task"); got != 0 {
		t.Fatalf("v1 wrote to task_articles: %d", got)
	}

	// H. Invalid versions then barrier.
	barrier6 := b7ArticleResult("b7-barrier-6", "hit-barrier-6", "accepted", "barrier6")
	b7PushBatch(t, redisClient, b7Marshal(t, barrier6),
		[]byte(`{"protocol_version":null,"task_id":"bad"}`),
		[]byte(`{"protocol_version":2.0,"task_id":"bad"}`),
		[]byte(`{"protocol_version":"9.9","task_id":"bad"}`),
		[]byte(`[1,2,3]`),
	)
	b7WaitFor(t, "invalid barrier", func() bool {
		return b7Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b7-barrier-6", "hit-barrier-6") == 1
	})

	// Final queue drain.
	b7WaitFor(t, "crawler:result empty", func() bool {
		n, err := redisClient.LLen(ctx, "crawler:result").Result()
		return err == nil && n == 0
	})
	if err := redisClient.Del(ctx, "crawler:result").Err(); err != nil {
		t.Fatalf("clean result key: %v", err)
	}
	fmt.Println("B7 worker E2E completed")
}
