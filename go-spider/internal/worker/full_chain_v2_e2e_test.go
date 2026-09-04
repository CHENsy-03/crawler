package worker

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"crawler-platform/internal/protocol"
	"crawler-platform/internal/queue"
	"crawler-platform/internal/store"

	"github.com/redis/go-redis/v9"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

func requireB8E2E(t *testing.T) {
	t.Helper()
	if os.Getenv("TASK019B8_E2E") != "1" {
		t.Skip("TASK019B8_E2E integration test is disabled")
	}
	for _, key := range []string{"TASK019B8_MYSQL_DSN", "TASK019B8_REDIS_ADDR", "TASK019B8_REPO_ROOT", "TASK019B8_PYTHON_EXE"} {
		if os.Getenv(key) == "" {
			t.Fatalf("%s is required for B8 E2E", key)
		}
	}
}

type b8Fixture struct {
	srv    *httptest.Server
	counts map[string]*atomic.Int32
}

func b8Hash(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func b8ArticleHTML(title, h1, bodyPrefix, date string) string {
	noise := "<script>bad()</script><nav>navtext</nav><header>headertext</header><footer>footertext</footer><aside>sidetext</aside>"
	paras := strings.Repeat("<p>"+bodyPrefix+"</p>", 700)
	return "<!doctype html><html><head><meta charset=\"utf-8\"><title>" + title + "</title>" +
		"<meta property=\"article:published_time\" content=\"" + date + "\">" +
		"<link rel=\"canonical\" href=\"/canonical/article\"></head><body>" + noise +
		"<h1>" + h1 + "</h1><div class=\"article-content\">" + paras + "</div></body></html>"
}

func newB8Fixture(t *testing.T) *b8Fixture {
	t.Helper()
	f := &b8Fixture{counts: map[string]*atomic.Int32{}}
	paths := []string{"/redirect", "/article", "/canonical/article", "/empty", "/irrelevant", "/expanded", "/snippet-only", "/unsupported.pdf"}
	for _, path := range paths {
		f.counts[path] = &atomic.Int32{}
	}
	mux := http.NewServeMux()
	wrap := func(path string, handler http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			f.counts[path].Add(1)
			handler(w, r)
		}
	}

	mux.HandleFunc("/redirect", wrap("/redirect", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/article", http.StatusFound)
	}))
	mux.HandleFunc("/article", wrap("/article", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(b8ArticleHTML("完全不同的标题", "低空经济政策发布", "低空经济政策正文内容", "2026-08-10T08:00:00Z")))
	}))
	mux.HandleFunc("/canonical/article", wrap("/canonical/article", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("canonical must not be fetched"))
	}))
	mux.HandleFunc("/empty", wrap("/empty", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte("<!doctype html><html><head><script>bad()</script></head><body></body></html>"))
	}))
	mux.HandleFunc("/irrelevant", wrap("/irrelevant", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(b8ArticleHTML("普通标题", "普通财经资讯", "普通财经正文内容", "2026-08-11T08:00:00Z")))
	}))
	mux.HandleFunc("/expanded", wrap("/expanded", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(b8ArticleHTML("无人机标题", "无人机产业动态", "无人机行业政策内容", "2026-08-12T08:00:00Z")))
	}))
	mux.HandleFunc("/snippet-only", wrap("/snippet-only", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(b8ArticleHTML("普通新闻标题", "普通新闻标题", "普通新闻正文内容", "2026-08-13T08:00:00Z")))
	}))
	mux.HandleFunc("/unsupported.pdf", wrap("/unsupported.pdf", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/pdf")
		_, _ = w.Write([]byte("fake pdf body"))
	}))

	f.srv = httptest.NewServer(mux)
	t.Cleanup(f.srv.Close)
	return f
}

func (f *b8Fixture) count(path string) int32 {
	return f.counts[path].Load()
}

func b8URLMessage(taskID, hitID, path, original, query, snippet, published string, f *b8Fixture) *protocol.URLMessageV2 {
	return &protocol.URLMessageV2{
		ProtocolVersion: protocol.VersionV2,
		TaskID:          taskID,
		MessageID:       taskID + "-" + hitID,
		Timestamp:       "2026-08-14T00:00:00Z",
		Type:            protocol.TypeURLV2,
		HitID:           hitID,
		PlanID:          "plan-b8",
		OriginalQuery:   original,
		QueryTerm:       query,
		URL:             f.srv.URL + path,
		Title:           "搜索标题",
		Snippet:         snippet,
		PublishedAt:     published,
		Source:          "127.0.0.1",
		Level:           0,
	}
}

func b8Marshal(t *testing.T, msg any) []byte {
	t.Helper()
	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return data
}

func b8PushURL(t *testing.T, client *redis.Client, msg *protocol.URLMessageV2) {
	t.Helper()
	if err := client.LPush(context.Background(), "crawler:url", b8Marshal(t, msg)).Err(); err != nil {
		t.Fatalf("push url: %v", err)
	}
}

func b8PushURLBatch(t *testing.T, client *redis.Client, barrier *protocol.URLMessageV2, extras ...[]byte) {
	t.Helper()
	_, err := client.TxPipelined(context.Background(), func(pipe redis.Pipeliner) error {
		if err := pipe.LPush(context.Background(), "crawler:url", b8Marshal(t, barrier)).Err(); err != nil {
			return err
		}
		for _, raw := range extras {
			if err := pipe.LPush(context.Background(), "crawler:url", raw).Err(); err != nil {
				return err
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("push url batch: %v", err)
	}
}

func b8OpenGorm(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(mysql.Open(os.Getenv("TASK019B8_MYSQL_DSN")), &gorm.Config{})
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

type b8KeyEventCounts struct {
	HTML   int
	Result int
	Error  int
}

type b8KeyEventRecorder struct {
	mu     sync.Mutex
	html   int
	result int
	err    int
	done   chan struct{}
	wg     sync.WaitGroup
	ps     *redis.PubSub
}

func (r *b8KeyEventRecorder) run() {
	defer r.wg.Done()
	for {
		select {
		case <-r.done:
			return
		default:
		}
		msg, err := r.ps.ReceiveTimeout(context.Background(), 250*time.Millisecond)
		if err != nil {
			continue
		}
		event, ok := msg.(*redis.Message)
		if !ok {
			continue
		}
		r.mu.Lock()
		switch event.Payload {
		case "crawler:html":
			r.html++
		case "crawler:result":
			r.result++
		case "crawler:error":
			r.err++
		}
		r.mu.Unlock()
	}
}

func (r *b8KeyEventRecorder) snapshot() b8KeyEventCounts {
	r.mu.Lock()
	defer r.mu.Unlock()
	return b8KeyEventCounts{HTML: r.html, Result: r.result, Error: r.err}
}

func (r *b8KeyEventRecorder) waitForEvents(t *testing.T, base b8KeyEventCounts, html, result, err int) {
	t.Helper()
	b8WaitFor(t, "keyevent counts", func() bool {
		current := r.snapshot()
		return current.HTML-base.HTML == html && current.Result-base.Result == result && current.Error-base.Error == err
	})
}

func b8StartKeyEventRecorder(t *testing.T, client *redis.Client) *b8KeyEventRecorder {
	t.Helper()
	ctx := context.Background()
	original, err := client.ConfigGet(ctx, "notify-keyspace-events").Result()
	if err != nil {
		t.Fatalf("config get notify-keyspace-events: %v", err)
	}
	originalValue := original["notify-keyspace-events"]
	if err := client.ConfigSet(ctx, "notify-keyspace-events", "KEA").Err(); err != nil {
		t.Fatalf("config set notify-keyspace-events: %v", err)
	}
	ps := client.PSubscribe(ctx, "__keyevent@0__:lpush", "__keyevent@0__:rpush")
	recorder := &b8KeyEventRecorder{done: make(chan struct{}), ps: ps}
	deadline := time.Now().Add(5 * time.Second)
	subscribed := false
	for !subscribed {
		msg, err := ps.ReceiveTimeout(ctx, 250*time.Millisecond)
		if err == nil {
			if sub, ok := msg.(*redis.Subscription); ok && sub.Kind == "psubscribe" && sub.Count == 2 {
				subscribed = true
			}
			continue
		}
		if time.Now().After(deadline) {
			_ = ps.Close()
			t.Fatalf("timed out waiting for keyevent subscription")
		}
	}
	recorder.wg.Add(1)
	go recorder.run()
	t.Cleanup(func() {
		close(recorder.done)
		recorder.wg.Wait()
		_ = ps.Close()
		if originalValue == "" {
			_ = client.ConfigSet(ctx, "notify-keyspace-events", "").Err()
		} else {
			_ = client.ConfigSet(ctx, "notify-keyspace-events", originalValue).Err()
		}
	})
	return recorder
}
func b8WaitFor(t *testing.T, desc string, cond func() bool) {
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

func b8Count(db *gorm.DB, table, where string, args ...any) int64 {
	var count int64
	if err := db.Table(table).Where(where, args...).Count(&count).Error; err != nil {
		return -1
	}
	return count
}

func b8WaitTask(t *testing.T, db *gorm.DB, taskID, hitID string) {
	t.Helper()
	b8WaitFor(t, "task_articles "+taskID+"/"+hitID, func() bool {
		return b8Count(db, "task_articles", "task_id = ? AND hit_id = ?", taskID, hitID) == 1
	})
}

func b8StartParser(t *testing.T, redisAddr string) (*exec.Cmd, *bytes.Buffer) {
	t.Helper()
	pythonExe := os.Getenv("TASK019B8_PYTHON_EXE")
	repoRoot := os.Getenv("TASK019B8_REPO_ROOT")
	runner := filepath.Join(repoRoot, "tests", "integration", "task019b8", "parser_runner.py")
	cmd := exec.Command(pythonExe, runner)
	cmd.Dir = repoRoot
	cmd.Env = append(os.Environ(),
		"TASK019B8_REDIS_ADDR="+redisAddr,
		"TASK019B8_REPO_ROOT="+repoRoot,
		"PYTHONUTF8=1",
		"PYTHONUNBUFFERED=1",
	)
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	if err := cmd.Start(); err != nil {
		t.Fatalf("start parser: %v", err)
	}
	t.Cleanup(func() {
		if cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
		_ = cmd.Wait()
	})
	return cmd, &buf
}

func b8StopParser(t *testing.T, cmd *exec.Cmd, buf *bytes.Buffer) {
	t.Helper()
	if cmd.Process != nil {
		_ = cmd.Process.Kill()
	}
	_ = cmd.Wait()
	_ = buf
}

func TestTask019B8LegacyBootstrap(t *testing.T) {
	requireB8E2E(t)
	s, err := store.NewMySQLStore(os.Getenv("TASK019B8_MYSQL_DSN"))
	if err != nil {
		t.Fatalf("NewMySQLStore: %v", err)
	}
	db := b8OpenGorm(t)
	var names []string
	if err := db.Raw("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()").Scan(&names).Error; err != nil {
		t.Fatal(err)
	}
	set := map[string]bool{}
	for _, name := range names {
		set[name] = true
	}
	for _, name := range []string{"article", "task", "crawl_log"} {
		if !set[name] {
			t.Fatalf("legacy table %s missing", name)
		}
	}
	for _, name := range []string{"articles", "task_articles", "tasks", "crawl_logs"} {
		if set[name] {
			t.Fatalf("v2/plural table %s must not exist before migration", name)
		}
	}
	_ = s
}

func TestTask019B8SchemaAfterMigration(t *testing.T) {
	requireB8E2E(t)
	_, err := store.NewMySQLStore(os.Getenv("TASK019B8_MYSQL_DSN"))
	if err != nil {
		t.Fatalf("NewMySQLStore: %v", err)
	}
	db := b8OpenGorm(t)
	var names []string
	if err := db.Raw("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()").Scan(&names).Error; err != nil {
		t.Fatal(err)
	}
	set := map[string]bool{}
	for _, name := range names {
		set[name] = true
	}
	for _, name := range []string{"article", "task", "crawl_log", "articles", "task_articles"} {
		if !set[name] {
			t.Fatalf("table %s missing after migration", name)
		}
	}
}

func TestTask019B8FullChain(t *testing.T) {
	requireB8E2E(t)

	ctx := context.Background()
	fixture := newB8Fixture(t)
	redisAddr := os.Getenv("TASK019B8_REDIS_ADDR")
	rq := queue.NewRedisQueue(redisAddr)
	redisClient := redis.NewClient(&redis.Options{Addr: redisAddr})
	t.Cleanup(func() { _ = redisClient.Close() })
	keyEvents := b8StartKeyEventRecorder(t, redisClient)
	for _, key := range []string{"crawler:url", "crawler:html", "crawler:result", "crawler:error", "crawler:event"} {
		if err := redisClient.Del(ctx, key).Err(); err != nil {
			t.Fatalf("reset %s: %v", key, err)
		}
	}

	db := b8OpenGorm(t)
	for _, statement := range []string{"DELETE FROM task_articles", "DELETE FROM articles", "DELETE FROM article", "DELETE FROM task"} {
		if err := db.Exec(statement).Error; err != nil {
			t.Fatalf("clean isolated db: %v", err)
		}
	}

	// Phase 1: download-only pool.
	pool1 := NewPool(2, rq, nil)
	pool1.Start()
	pool1Stopped := false
	defer func() {
		if !pool1Stopped {
			pool1.Stop()
		}
	}()

	multi1 := b8URLMessage("b8-multi", "hit-multi-1", "/redirect", "低空经济", "低空经济", "", "2026-01-01", fixture)
	multi2 := b8URLMessage("b8-multi", "hit-multi-2", "/redirect", "低空经济", "低空经济", "", "2026-01-01", fixture)
	b8PushURL(t, redisClient, multi1)
	b8PushURL(t, redisClient, multi2)
	b8WaitFor(t, "two html messages", func() bool {
		n, err := redisClient.LLen(ctx, "crawler:html").Result()
		return err == nil && n == 2
	})

	htmlVals, err := redisClient.LRange(ctx, "crawler:html", 0, -1).Result()
	if err != nil {
		t.Fatal(err)
	}
	htmlHits := map[string]bool{}
	for _, value := range htmlVals {
		decoded, err := protocol.DecodeV2ArticleMessage([]byte(value))
		if err != nil {
			t.Fatalf("decode html_v2: %v", err)
		}
		html, ok := decoded.(*protocol.HTMLMessageV2)
		if !ok {
			t.Fatalf("unexpected html type %T", decoded)
		}
		htmlHits[html.HitID] = true
		if html.RequestedURL != fixture.srv.URL+"/redirect" || html.FinalURL != fixture.srv.URL+"/article" {
			t.Fatalf("unexpected html urls: %+v", html)
		}
	}
	if !htmlHits["hit-multi-1"] || !htmlHits["hit-multi-2"] {
		t.Fatalf("missing hit ids in html: %#v", htmlHits)
	}
	if fixture.count("/redirect") != 1 || fixture.count("/article") != 1 {
		t.Fatalf("download counts redirect=%d article=%d", fixture.count("/redirect"), fixture.count("/article"))
	}

	// Phase 2: Python parser subprocess.
	parserCmd, parserBuf := b8StartParser(t, redisAddr)
	defer b8StopParser(t, parserCmd, parserBuf)
	b8WaitFor(t, "parser consumes html and publishes two results", func() bool {
		htmlLen, _ := redisClient.LLen(ctx, "crawler:html").Result()
		resLen, _ := redisClient.LLen(ctx, "crawler:result").Result()
		return htmlLen == 0 && resLen == 2
	})

	resultVals, err := redisClient.LRange(ctx, "crawler:result", 0, -1).Result()
	if err != nil {
		t.Fatal(err)
	}
	resultHits := map[string]bool{}
	for _, value := range resultVals {
		decoded, err := protocol.DecodeV2ArticleMessage([]byte(value))
		if err != nil {
			t.Fatalf("decode article_result: %v", err)
		}
		article, ok := decoded.(*protocol.ArticleResultV2)
		if !ok {
			t.Fatalf("unexpected result type %T", decoded)
		}
		if article.Status != "accepted" {
			t.Fatalf("multi-hit result status = %s", article.Status)
		}
		resultHits[article.HitID] = true
	}
	if !resultHits["hit-multi-1"] || !resultHits["hit-multi-2"] {
		t.Fatalf("missing hit ids in results: %#v", resultHits)
	}

	// Phase 3: stop download pool and start persistence pool.
	pool1.Stop()
	pool1Stopped = true
	// StartRedisConsumer is not tracked by WaitGroup; allow its blocked BRPOP to exit.
	time.Sleep(4 * time.Second)

	myStore, err := store.NewMySQLStore(os.Getenv("TASK019B8_MYSQL_DSN"))
	if err != nil {
		t.Fatalf("NewMySQLStore: %v", err)
	}
	pool2 := NewPool(2, rq, myStore)
	pool2.Start()
	defer pool2.Stop()

	b8WaitTask(t, db, "b8-multi", "hit-multi-1")
	b8WaitTask(t, db, "b8-multi", "hit-multi-2")

	var multiRows []struct {
		ArticleID        *uint64
		Status           string
		ExtractionMethod string
		ContentHash      string
		RequestedURL     string
		FinalURL         string
		CanonicalURL     string
		Title            string
		PublishDate      *time.Time
		Source           string
	}
	if err := db.Table("task_articles").Where("task_id = ?", "b8-multi").Scan(&multiRows).Error; err != nil {
		t.Fatal(err)
	}
	if len(multiRows) != 2 || multiRows[0].ArticleID == nil || multiRows[1].ArticleID == nil || *multiRows[0].ArticleID != *multiRows[1].ArticleID {
		t.Fatalf("multi-hit article linkage mismatch: %+v", multiRows)
	}
	row := multiRows[0]
	if row.Status != "accepted" || row.ExtractionMethod != "fallback" {
		t.Fatalf("accepted/fallback mismatch: %+v", row)
	}
	if row.RequestedURL != fixture.srv.URL+"/redirect" || row.FinalURL != fixture.srv.URL+"/article" || row.CanonicalURL != fixture.srv.URL+"/canonical/article" {
		t.Fatalf("url semantics mismatch: %+v", row)
	}
	if row.Title != "低空经济政策发布" || row.Source != "127.0.0.1" {
		t.Fatalf("title/source mismatch: %+v", row)
	}
	if row.PublishDate == nil || row.PublishDate.Format("2006-01-02") != "2026-08-10" {
		t.Fatalf("detail date must win over published_at: %v", row.PublishDate)
	}

	var articleRow struct {
		Content     string
		ContentHash string
	}
	if err := db.Table("articles").Where("id = ?", *row.ArticleID).Scan(&articleRow).Error; err != nil {
		t.Fatal(err)
	}
	if len(articleRow.Content) <= 5000 || articleRow.ContentHash != b8Hash(articleRow.Content) {
		t.Fatalf("long content/hash mismatch len=%d", len(articleRow.Content))
	}
	for _, noise := range []string{"navtext", "headertext", "footertext", "sidetext", "bad()"} {
		if strings.Contains(articleRow.Content, noise) {
			t.Fatalf("noise %q leaked into content", noise)
		}
	}
	if got := b8Count(db, "articles", "content_hash = ?", articleRow.ContentHash); got != 1 {
		t.Fatalf("multi-hit must share one article, got %d", got)
	}

	// Expanded-only.
	expanded := b8URLMessage("b8-expanded", "hit-expanded", "/expanded", "低空经济", "无人机", "", "", fixture)
	b8PushURL(t, redisClient, expanded)
	b8WaitTask(t, db, "b8-expanded", "hit-expanded")
	var expandedRow struct {
		Status          string
		MatchedEvidence string
		ArticleID       *uint64
	}
	if err := db.Table("task_articles").Select("status, matched_evidence, article_id").Where("task_id = ?", "b8-expanded").Scan(&expandedRow).Error; err != nil {
		t.Fatal(err)
	}
	var expandedEvidence []protocol.MatchedEvidence
	if err := json.Unmarshal([]byte(expandedRow.MatchedEvidence), &expandedEvidence); err != nil {
		t.Fatal(err)
	}
	if expandedRow.Status != "review_required" || expandedRow.ArticleID == nil || len(expandedEvidence) == 0 {
		t.Fatalf("expanded-only mismatch: %+v", expandedRow)
	}
	for _, evidence := range expandedEvidence {
		if evidence.Origin != "expanded" {
			t.Fatalf("expanded evidence origin = %s", evidence.Origin)
		}
	}

	// Snippet-only.
	snippet := b8URLMessage("b8-snippet", "hit-snippet", "/snippet-only", "低空经济", "低空经济", "低空经济摘要", "", fixture)
	b8PushURL(t, redisClient, snippet)
	b8WaitTask(t, db, "b8-snippet", "hit-snippet")
	var snippetRow struct {
		Status          string
		MatchedEvidence string
	}
	if err := db.Table("task_articles").Select("status, matched_evidence").Where("task_id = ?", "b8-snippet").Scan(&snippetRow).Error; err != nil {
		t.Fatal(err)
	}
	var snippetEvidence []protocol.MatchedEvidence
	if err := json.Unmarshal([]byte(snippetRow.MatchedEvidence), &snippetEvidence); err != nil {
		t.Fatal(err)
	}
	if snippetRow.Status != "review_required" || len(snippetEvidence) == 0 || snippetEvidence[0].Field != "summary" {
		t.Fatalf("snippet-only mismatch: %+v evidence=%+v", snippetRow, snippetEvidence)
	}

	// Irrelevant.
	irrelevant := b8URLMessage("b8-irrelevant", "hit-irrelevant", "/irrelevant", "低空经济", "低空经济", "", "", fixture)
	b8PushURL(t, redisClient, irrelevant)
	b8WaitTask(t, db, "b8-irrelevant", "hit-irrelevant")
	var irrelevantRow struct {
		Status          string
		MatchedEvidence string
	}
	if err := db.Table("task_articles").Select("status, matched_evidence").Where("task_id = ?", "b8-irrelevant").Scan(&irrelevantRow).Error; err != nil {
		t.Fatal(err)
	}
	var irrelevantEvidence []protocol.MatchedEvidence
	if err := json.Unmarshal([]byte(irrelevantRow.MatchedEvidence), &irrelevantEvidence); err != nil {
		t.Fatal(err)
	}
	if irrelevantRow.Status != "irrelevant" || len(irrelevantEvidence) != 0 {
		t.Fatalf("irrelevant mismatch: %+v evidence=%+v", irrelevantRow, irrelevantEvidence)
	}

	// Extract failed.
	empty := b8URLMessage("b8-empty", "hit-empty", "/empty", "低空经济", "低空经济", "", "", fixture)
	b8PushURL(t, redisClient, empty)
	b8WaitTask(t, db, "b8-empty", "hit-empty")
	var emptyRow struct {
		Status           string
		ExtractionMethod string
		ContentHash      string
		ArticleID        *uint64
	}
	if err := db.Table("task_articles").Select("status, extraction_method, content_hash, article_id").Where("task_id = ?", "b8-empty").Scan(&emptyRow).Error; err != nil {
		t.Fatal(err)
	}
	if emptyRow.Status != "extract_failed" || emptyRow.ExtractionMethod != "none" || emptyRow.ContentHash != "" || emptyRow.ArticleID != nil {
		t.Fatalf("extract_failed mismatch: %+v", emptyRow)
	}

	// Non-HTML MIME: wait until PDF URL is consumed before pushing barrier.
	pdfMsg := b8URLMessage("b8-pdf", "hit-pdf", "/unsupported.pdf", "低空经济", "低空经济", "", "", fixture)
	b8PushURL(t, redisClient, pdfMsg)
	b8WaitFor(t, "pdf consumed", func() bool {
		n, err := redisClient.LLen(ctx, "crawler:url").Result()
		return err == nil && n == 0 && fixture.count("/unsupported.pdf") == 1
	})
	barrierPdf := b8URLMessage("b8-pdf-barrier", "hit-pdf-barrier", "/irrelevant", "低空经济", "低空经济", "", "", fixture)
	b8PushURL(t, redisClient, barrierPdf)
	b8WaitTask(t, db, "b8-pdf-barrier", "hit-pdf-barrier")
	if got := b8Count(db, "task_articles", "task_id = ?", "b8-pdf"); got != 0 {
		t.Fatalf("pdf must not persist task_articles: %d", got)
	}
	if fixture.count("/unsupported.pdf") != 1 {
		t.Fatalf("pdf request count = %d", fixture.count("/unsupported.pdf"))
	}

	// Invalid URLMessageV2 values.
	barrierInvalid := b8URLMessage("b8-invalid-barrier", "hit-invalid-barrier", "/irrelevant", "低空经济", "低空经济", "", "", fixture)
	invalidRaw := []string{
		fmt.Sprintf(`{"protocol_version":"9.9","task_id":"b8-invalid-1","message_id":"m1","timestamp":"now","type":"url","hit_id":"h","plan_id":"p","original_query":"q","query_term":"q","url":"%s/irrelevant","title":"","snippet":"","published_at":"","source":"s","level":0}`, fixture.srv.URL),
		fmt.Sprintf(`{"protocol_version":null,"task_id":"b8-invalid-2","message_id":"m2","timestamp":"now","type":"url","hit_id":"h","plan_id":"p","original_query":"q","query_term":"q","url":"%s/irrelevant","title":"","snippet":"","published_at":"","source":"s","level":0}`, fixture.srv.URL),
		fmt.Sprintf(`{"protocol_version":"2.0","task_id":"b8-invalid-3","message_id":"m3","timestamp":"now","type":"url","hit_id":"h","original_query":"q","query_term":"q","url":"%s/irrelevant","title":"","snippet":"","published_at":"","source":"s","level":0,"unknown":true}`, fixture.srv.URL),
	}
	beforeNullLegacy := b8Count(db, "article", "1 = 1")
	beforeNullArticles := b8Count(db, "articles", "1 = 1")
	beforeNullTasks := b8Count(db, "task_articles", "1 = 1")
	beforeNullEvents := keyEvents.snapshot()
	beforeInvalidCount := fixture.count("/irrelevant")
	for _, value := range invalidRaw {
		if err := redisClient.LPush(ctx, "crawler:url", value).Err(); err != nil {
			t.Fatalf("push invalid url: %v", err)
		}
	}
	b8WaitFor(t, "invalid url messages consumed", func() bool {
		n, err := redisClient.LLen(ctx, "crawler:url").Result()
		return err == nil && n == 0
	})
	b8PushURL(t, redisClient, barrierInvalid)
	b8WaitTask(t, db, "b8-invalid-barrier", "hit-invalid-barrier")
	keyEvents.waitForEvents(t, beforeNullEvents, 1, 1, 0)
	if got := b8Count(db, "task_articles", "task_id IN (?, ?, ?)", "b8-invalid-1", "b8-invalid-2", "b8-invalid-3"); got != 0 {
		t.Fatalf("invalid messages wrote task_articles: %d", got)
	}
	if fixture.count("/irrelevant") != beforeInvalidCount+1 {
		t.Fatalf("invalid messages caused extra requests: before=%d after=%d", beforeInvalidCount, fixture.count("/irrelevant"))
	}
	if got := b8Count(db, "task_articles", "1 = 1"); got != beforeNullTasks+1 {
		t.Fatalf("null window task_articles delta = %d, want 1", got-beforeNullTasks)
	}
	if got := b8Count(db, "articles", "1 = 1"); got != beforeNullArticles {
		t.Fatalf("null window articles delta = %d, want 0", got-beforeNullArticles)
	}
	if got := b8Count(db, "article", "1 = 1"); got != beforeNullLegacy {
		t.Fatalf("null window legacy article delta = %d, want 0", got-beforeNullLegacy)
	}
	errorLen, err := redisClient.LLen(ctx, "crawler:error").Result()
	if err != nil {
		t.Fatal(err)
	}
	if errorLen != 0 {
		t.Fatalf("crawler:error length = %d after null window", errorLen)
	}

	// Duplicate delivery.
	dupMsg := b8URLMessage("b8-dup", "hit-dup", "/irrelevant", "低空经济", "低空经济", "", "", fixture)
	b8PushURL(t, redisClient, dupMsg)
	b8WaitTask(t, db, "b8-dup", "hit-dup")
	beforeDupEvents := keyEvents.snapshot()
	beforeDupLegacy := b8Count(db, "article", "1 = 1")
	beforeDupArticles := b8Count(db, "articles", "1 = 1")
	beforeDupTasks := b8Count(db, "task_articles", "1 = 1")
	beforeDupHit := b8Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b8-dup", "hit-dup")
	var beforeDupHash string
	if err := db.Table("task_articles").Select("result_hash").Where("task_id = ? AND hit_id = ?", "b8-dup", "hit-dup").Scan(&beforeDupHash).Error; err != nil {
		t.Fatal(err)
	}
	beforeDupCount := fixture.count("/irrelevant")
	b8PushURL(t, redisClient, dupMsg)
	b8WaitFor(t, "duplicate url consumed", func() bool {
		n, err := redisClient.LLen(ctx, "crawler:url").Result()
		return err == nil && n == 0
	})
	if fixture.count("/irrelevant") != beforeDupCount {
		t.Fatalf("duplicate caused extra HTTP request before barrier: before=%d after=%d", beforeDupCount, fixture.count("/irrelevant"))
	}
	barrierDup := b8URLMessage("b8-dup-barrier", "hit-dup-barrier", "/irrelevant", "低空经济", "低空经济", "", "", fixture)
	b8PushURL(t, redisClient, barrierDup)
	b8WaitTask(t, db, "b8-dup-barrier", "hit-dup-barrier")
	keyEvents.waitForEvents(t, beforeDupEvents, 1, 1, 0)
	if got := b8Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b8-dup", "hit-dup"); got != beforeDupHit {
		t.Fatalf("duplicate changed task_articles count: got=%d want=%d", got, beforeDupHit)
	}
	if got := b8Count(db, "task_articles", "task_id = ? AND hit_id = ?", "b8-dup-barrier", "hit-dup-barrier"); got != 1 {
		t.Fatalf("barrier task_articles count = %d", got)
	}
	if got := b8Count(db, "task_articles", "1 = 1"); got != beforeDupTasks+1 {
		t.Fatalf("duplicate window task_articles delta = %d, want 1", got-beforeDupTasks)
	}
	if got := b8Count(db, "articles", "1 = 1"); got != beforeDupArticles {
		t.Fatalf("duplicate window articles delta = %d, want 0", got-beforeDupArticles)
	}
	if got := b8Count(db, "article", "1 = 1"); got != beforeDupLegacy {
		t.Fatalf("duplicate window legacy article delta = %d, want 0", got-beforeDupLegacy)
	}
	var afterDupHash string
	if err := db.Table("task_articles").Select("result_hash").Where("task_id = ? AND hit_id = ?", "b8-dup", "hit-dup").Scan(&afterDupHash).Error; err != nil {
		t.Fatal(err)
	}
	if afterDupHash != beforeDupHash {
		t.Fatalf("duplicate changed result_hash: before=%s after=%s", beforeDupHash, afterDupHash)
	}
	if fixture.count("/irrelevant") != beforeDupCount+1 {
		t.Fatalf("barrier request count mismatch: before=%d after=%d", beforeDupCount, fixture.count("/irrelevant"))
	}

	if fixture.count("/canonical/article") != 0 {
		t.Fatalf("canonical URL was fetched %d times", fixture.count("/canonical/article"))
	}

	// Final queue drain and process shutdown.
	b8WaitFor(t, "queues empty", func() bool {
		for _, key := range []string{"crawler:url", "crawler:html", "crawler:result", "crawler:error"} {
			n, err := redisClient.LLen(ctx, key).Result()
			if err != nil || n != 0 {
				return false
			}
		}
		return true
	})
}
