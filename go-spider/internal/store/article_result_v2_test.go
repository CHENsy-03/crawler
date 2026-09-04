package store

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"crawler-platform/internal/protocol"
)

func validArticleResultV2() *protocol.ArticleResultV2 {
	content := "低空经济正文内容"
	return &protocol.ArticleResultV2{
		ProtocolVersion: protocol.VersionV2,
		TaskID:          "task-1",
		MessageID:       "msg-1",
		Timestamp:       "2026-08-13T10:00:00Z",
		Type:            protocol.TypeArticleResultV2,
		HitID:           "hit-1",
		PlanID:          "plan-1",
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
		ContentHash:     sha256Hex(content),
		Score:           5,
		MatchedEvidence: []protocol.MatchedEvidence{
			{Term: "低空经济", Origin: "original", Field: "title", Weight: 5},
		},
		Status:           "accepted",
		ExtractionMethod: "density",
	}
}

func TestTableNames(t *testing.T) {
	if (ArticleV2{}).TableName() != "articles" {
		t.Fatalf("ArticleV2 table = %q", (ArticleV2{}).TableName())
	}
	if (TaskArticleV2{}).TableName() != "task_articles" {
		t.Fatalf("TaskArticleV2 table = %q", (TaskArticleV2{}).TableName())
	}
}

func TestIdentityUsesCanonicalURLWhenPresent(t *testing.T) {
	records, err := BuildArticleResultV2Records(validArticleResultV2())
	if err != nil {
		t.Fatal(err)
	}
	if records.IdentityURL != "https://example.gov.cn/canonical" {
		t.Fatalf("identity_url = %q", records.IdentityURL)
	}
	if records.Article.IdentityURL != records.IdentityURL {
		t.Fatalf("article identity_url mismatch")
	}
}

func TestIdentityUsesFinalURLWhenCanonicalEmpty(t *testing.T) {
	msg := validArticleResultV2()
	msg.CanonicalURL = ""
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if records.IdentityURL != msg.FinalURL {
		t.Fatalf("identity_url = %q", records.IdentityURL)
	}
}

func TestRequestedURLDoesNotBecomeIdentity(t *testing.T) {
	records, err := BuildArticleResultV2Records(validArticleResultV2())
	if err != nil {
		t.Fatal(err)
	}
	if records.IdentityURL == records.TaskArticle.RequestedURL {
		t.Fatalf("requested_url must not be article identity")
	}
}

func TestIdentityAndArticleKeyStable(t *testing.T) {
	a, err := BuildArticleResultV2Records(validArticleResultV2())
	if err != nil {
		t.Fatal(err)
	}
	b, err := BuildArticleResultV2Records(validArticleResultV2())
	if err != nil {
		t.Fatal(err)
	}
	if a.IdentityURLHash != b.IdentityURLHash || a.ArticleKey != b.ArticleKey || a.ResultHash != b.ResultHash {
		t.Fatalf("identity/result hashes are not stable")
	}
}

func TestArticleKeyChangesWhenContentHashChanges(t *testing.T) {
	msg := validArticleResultV2()
	first, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	msg.Content = "低空经济正文内容 v2"
	msg.ContentHash = sha256Hex(msg.Content)
	second, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if first.ArticleKey == second.ArticleKey {
		t.Fatalf("article_key must change with content_hash")
	}
}

func TestArticleKeyChangesWhenURLChanges(t *testing.T) {
	msg := validArticleResultV2()
	first, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	msg.CanonicalURL = "https://example.gov.cn/other"
	second, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if first.ArticleKey == second.ArticleKey {
		t.Fatalf("article_key must change with identity_url")
	}
}

func TestFullContentPreserved(t *testing.T) {
	msg := validArticleResultV2()
	msg.Content = strings.Repeat("低空经济正文", 2000)
	msg.ContentHash = sha256Hex(msg.Content)
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if records.Article == nil {
		t.Fatal("expected article record")
	}
	if records.Article.Content != msg.Content {
		t.Fatalf("content was not preserved")
	}
}

func TestEmptyContentCreatesNoArticle(t *testing.T) {
	msg := validArticleResultV2()
	msg.Content = ""
	msg.ContentHash = ""
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if records.Article != nil {
		t.Fatalf("empty content must not create ArticleV2")
	}
	if records.TaskArticle.Status != msg.Status {
		t.Fatalf("task article status = %q", records.TaskArticle.Status)
	}
}

func TestExtractFailedStillCreatesTaskArticle(t *testing.T) {
	msg := validArticleResultV2()
	msg.Content = ""
	msg.ContentHash = ""
	msg.Status = "extract_failed"
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if records.Article != nil || records.TaskArticle.Status != "extract_failed" {
		t.Fatalf("extract_failed mapping mismatch")
	}
}

func TestUnsupportedFormatPreserved(t *testing.T) {
	msg := validArticleResultV2()
	msg.Content = ""
	msg.ContentHash = ""
	msg.Status = "unsupported_format"
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if records.TaskArticle.Status != "unsupported_format" {
		t.Fatalf("unsupported_format not preserved")
	}
}

func TestPublishDateEmptyIsNil(t *testing.T) {
	msg := validArticleResultV2()
	msg.PublishDate = ""
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if records.PublishDate != nil || records.Article.PublishDate != nil || records.TaskArticle.PublishDate != nil {
		t.Fatalf("empty publish_date must map to NULL")
	}
}

func TestPublishDateValid(t *testing.T) {
	records, err := BuildArticleResultV2Records(validArticleResultV2())
	if err != nil {
		t.Fatal(err)
	}
	if records.PublishDate == nil || records.PublishDate.Format("2006-01-02") != "2026-08-13" {
		t.Fatalf("publish_date mapping failed")
	}
}

func TestPublishDateInvalidRejected(t *testing.T) {
	msg := validArticleResultV2()
	msg.PublishDate = "not-a-date"
	if _, err := BuildArticleResultV2Records(msg); err == nil {
		t.Fatal("expected invalid publish_date error")
	}
}

func TestResultTimestampParsed(t *testing.T) {
	records, err := BuildArticleResultV2Records(validArticleResultV2())
	if err != nil {
		t.Fatal(err)
	}
	if records.ResultTimestamp.IsZero() {
		t.Fatal("result timestamp should be parsed")
	}
}

func TestResultTimestampInvalidRejected(t *testing.T) {
	msg := validArticleResultV2()
	msg.Timestamp = "not-a-time"
	if _, err := BuildArticleResultV2Records(msg); err == nil {
		t.Fatal("expected invalid timestamp error")
	}
}

func TestEmptyEvidenceSerializesToArray(t *testing.T) {
	msg := validArticleResultV2()
	msg.MatchedEvidence = nil
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if records.MatchedEvidenceJSON != "[]" {
		t.Fatalf("evidence JSON = %q", records.MatchedEvidenceJSON)
	}
	if records.TaskArticle.MatchedEvidence != "[]" {
		t.Fatalf("task article evidence = %q", records.TaskArticle.MatchedEvidence)
	}
}

func TestEvidenceOrderPreserved(t *testing.T) {
	msg := validArticleResultV2()
	msg.MatchedEvidence = []protocol.MatchedEvidence{
		{Term: "甲", Origin: "original", Field: "title", Weight: 5},
		{Term: "乙", Origin: "expanded", Field: "content", Weight: 1},
	}
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(records.MatchedEvidenceJSON, `"term":"甲"`) ||
		!strings.Contains(records.MatchedEvidenceJSON, `"term":"乙"`) {
		t.Fatalf("evidence order/content missing: %s", records.MatchedEvidenceJSON)
	}
	if strings.Index(records.MatchedEvidenceJSON, "甲") > strings.Index(records.MatchedEvidenceJSON, "乙") {
		t.Fatalf("evidence order changed")
	}
}

func TestValidateFailureStopsMapping(t *testing.T) {
	msg := validArticleResultV2()
	msg.Score = -1
	if _, err := BuildArticleResultV2Records(msg); err == nil {
		t.Fatal("expected validation error")
	}
}

func TestResultHashIgnoresMessageIDAndTimestamp(t *testing.T) {
	msg := validArticleResultV2()
	first, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	msg.MessageID = "msg-999"
	msg.Timestamp = "2026-08-14T11:00:00Z"
	second, err := BuildArticleResultV2Records(msg)
	if err != nil {
		t.Fatal(err)
	}
	if first.ResultHash != second.ResultHash {
		t.Fatalf("result_hash must ignore message_id and timestamp")
	}
}

func TestResultHashChangesWithBusinessFields(t *testing.T) {
	base := validArticleResultV2()
	baseline, err := BuildArticleResultV2Records(base)
	if err != nil {
		t.Fatal(err)
	}

	cases := []func(*protocol.ArticleResultV2){
		func(m *protocol.ArticleResultV2) { m.Score = 6 },
		func(m *protocol.ArticleResultV2) { m.Status = "review_required" },
		func(m *protocol.ArticleResultV2) {
			m.MatchedEvidence = append(m.MatchedEvidence, protocol.MatchedEvidence{Term: "x", Origin: "original", Field: "url", Weight: 0})
		},
		func(m *protocol.ArticleResultV2) {
			m.Content = "新正文"
			m.ContentHash = sha256Hex(m.Content)
		},
	}
	for _, change := range cases {
		msg := validArticleResultV2()
		change(msg)
		records, err := BuildArticleResultV2Records(msg)
		if err != nil {
			t.Fatal(err)
		}
		if records.ResultHash == baseline.ResultHash {
			t.Fatalf("result_hash must change with business fields")
		}
	}
}

func repoRootForTest() string {
	_, file, _, _ := runtime.Caller(0)
	return filepath.Join(filepath.Dir(file), "..", "..", "..")
}

func TestMigrationIsAdditiveAndHasRequiredColumns(t *testing.T) {
	path := filepath.Join(repoRootForTest(), "migrations", "mysql", "0001_articles_task_articles_v2.sql")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	sql := string(data)
	for _, forbidden := range []string{"DROP", "TRUNCATE", "RENAME TABLE", "ALTER TABLE", "DELETE FROM"} {
		if strings.Contains(sql, forbidden) {
			t.Fatalf("migration contains forbidden SQL %q", forbidden)
		}
	}
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS articles",
		"CREATE TABLE IF NOT EXISTS task_articles",
		"content            LONGTEXT NOT NULL",
		"matched_evidence    JSON NOT NULL",
		"article_id          BIGINT UNSIGNED NULL",
		"UNIQUE KEY uq_articles_article_key",
		"UNIQUE KEY uq_task_articles_task_hit",
		"KEY idx_articles_identity_url_hash",
		"KEY idx_articles_content_hash",
		"KEY idx_articles_publish_date",
		"KEY idx_task_articles_task_status",
		"KEY idx_task_articles_article_id",
		"KEY idx_task_articles_plan_id",
		"KEY idx_task_articles_content_hash",
	} {
		if !strings.Contains(sql, required) {
			t.Fatalf("migration missing %q", required)
		}
	}
	if strings.Contains(sql, "raw_html") || strings.Contains(sql, "attachment") || strings.Contains(sql, "html LONGTEXT") {
		t.Fatalf("migration must not contain raw HTML or attachment columns")
	}
}

func TestBootstrapSchemaContainsV2Tables(t *testing.T) {
	path := filepath.Join(repoRootForTest(), "config", "schema.sql")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	sql := string(data)
	if !strings.Contains(sql, "CREATE TABLE IF NOT EXISTS articles") ||
		!strings.Contains(sql, "CREATE TABLE IF NOT EXISTS task_articles") {
		t.Fatalf("config/schema.sql must contain v2 tables")
	}
}

func TestNewStoreFilesDoNotReferenceRawHTMLOrUpdateTask(t *testing.T) {
	dir := filepath.Join(repoRootForTest(), "go-spider", "internal", "store")
	for _, name := range []string{"article_result_v2.go", "article_result_v2_persistence.go"} {
		data, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			t.Fatal(err)
		}
		text := string(data)
		if strings.Contains(text, "raw_html") || strings.Contains(text, "attachment") || strings.Contains(text, "UpdateTask") || strings.Contains(text, "article_count") {
			t.Fatalf("%s must not contain raw HTML/attachment/UpdateTask/article_count", name)
		}
	}
}

func TestPersistenceNotWiredOutsideStore(t *testing.T) {
	root := repoRootForTest()
	targets := []string{
		filepath.Join(root, "go-spider", "main.go"),
	}
	for _, dir := range []string{
		filepath.Join(root, "go-spider", "internal", "queue"),
		filepath.Join(root, "go-spider", "internal", "worker"),
		filepath.Join(root, "go-spider", "internal", "api"),
	} {
		err := filepath.WalkDir(dir, func(path string, entry os.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if entry.IsDir() || filepath.Ext(path) != ".go" || strings.HasSuffix(path, "_test.go") {
				return nil
			}
			targets = append(targets, path)
			return nil
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	for _, path := range targets {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		text := string(data)
		for _, symbol := range []string{"PersistArticleResultV2", "ArticleV2", "TaskArticleV2"} {
			if strings.Contains(text, symbol) && !(symbol == "PersistArticleResultV2" && strings.HasSuffix(path, "worker"+string(os.PathSeparator)+"pool.go")) {
				t.Fatalf("%s must not reference %s", path, symbol)
			}
		}
	}
}

func TestLegacyStoreAndConsumersRemain(t *testing.T) {
	root := repoRootForTest()
	mysqlSource, err := os.ReadFile(filepath.Join(root, "go-spider", "internal", "store", "mysql.go"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(mysqlSource), "AutoMigrate(&Article{}, &Task{}, &CrawlLog{})") {
		t.Fatalf("legacy AutoMigrate must remain unchanged")
	}
	if strings.Contains(string(mysqlSource), "ArticleV2") || strings.Contains(string(mysqlSource), "TaskArticleV2") {
		t.Fatalf("legacy AutoMigrate must not include v2 models")
	}

	queueSource, err := os.ReadFile(filepath.Join(root, "go-spider", "internal", "queue", "redis.go"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(queueSource), "func (rq *RedisQueue) PopResultMessage") {
		t.Fatalf("PopResultMessage v1 path must remain")
	}

	workerSource, err := os.ReadFile(filepath.Join(root, "go-spider", "internal", "worker", "pool.go"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(workerSource), "StartResultConsumer") {
		t.Fatalf("StartResultConsumer must remain")
	}
}
