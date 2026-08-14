package worker

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"strings"
	"testing"

	"crawler-platform/internal/protocol"
	"crawler-platform/internal/queue"
	"crawler-platform/internal/store"
)

type fakeV2AwareStore struct {
	persist      func(context.Context, *protocol.ArticleResultV2) (store.PersistArticleResultV2Outcome, error)
	saveCalls    int
	updateCalls  int
	persistCalls int
}

func (f *fakeV2AwareStore) PersistArticleResultV2(ctx context.Context, msg *protocol.ArticleResultV2) (store.PersistArticleResultV2Outcome, error) {
	f.persistCalls++
	if f.persist != nil {
		return f.persist(ctx, msg)
	}
	return store.PersistArticleResultV2Outcome{TaskArticleID: 1, Inserted: true}, nil
}

func (f *fakeV2AwareStore) SaveArticle(*store.Article) error {
	f.saveCalls++
	return nil
}

func (f *fakeV2AwareStore) UpdateTask(id, status string, count int) error {
	f.updateCalls++
	return nil
}

func workerArticleResult(status, content string) *protocol.ArticleResultV2 {
	contentHash := ""
	if content != "" {
		sum := sha256.Sum256([]byte(content))
		contentHash = hex.EncodeToString(sum[:])
	}
	return &protocol.ArticleResultV2{
		ProtocolVersion: protocol.VersionV2,
		TaskID:          "task-v2",
		MessageID:       "msg-v2",
		Timestamp:       "2026-08-13T10:00:00Z",
		Type:            protocol.TypeArticleResultV2,
		HitID:           "hit-v2",
		PlanID:          "plan-v2",
		OriginalQuery:   "低空经济",
		QueryTerm:       "低空经济",
		RequestedURL:    "https://example.gov.cn/requested",
		FinalURL:        "https://example.gov.cn/final",
		CanonicalURL:    "https://example.gov.cn/canonical",
		Title:           "标题",
		PublishDate:     "2026-08-13",
		Source:          "example.gov.cn",
		Summary:         "摘要",
		Content:         content,
		ContentHash:     contentHash,
		Score:           5,
		MatchedEvidence: []protocol.MatchedEvidence{
			{Term: "低空经济", Origin: "original", Field: "title", Weight: 5},
		},
		Status:           status,
		ExtractionMethod: "density",
	}
}

func legacyResultMessage() *protocol.ResultMessage {
	return &protocol.ResultMessage{
		Envelope: protocol.Envelope{TaskID: "task-legacy"},
		URL:      "https://example.gov.cn/a.html",
		Site:     "s",
		Keyword:  "k",
		Title:    "T",
		Content:  "C",
		Score:    1,
	}
}

func TestHandleResultDispatchLegacyUsesConsumeResult(t *testing.T) {
	fs := &fakeV2AwareStore{}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchLegacy, Message: legacyResultMessage()}
	if err := p.handleResultDispatch(dispatch); err != nil {
		t.Fatal(err)
	}
	if fs.saveCalls == 0 || fs.updateCalls == 0 {
		t.Fatalf("legacy must use old storage: save=%d update=%d", fs.saveCalls, fs.updateCalls)
	}
	if fs.persistCalls != 0 {
		t.Fatalf("legacy must not call v2 persistence")
	}
}

func TestHandleResultDispatchV1UsesConsumeResult(t *testing.T) {
	fs := &fakeV2AwareStore{}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchV1, Message: legacyResultMessage()}
	if err := p.handleResultDispatch(dispatch); err != nil {
		t.Fatal(err)
	}
	if fs.saveCalls == 0 || fs.updateCalls == 0 || fs.persistCalls != 0 {
		t.Fatalf("v1 storage path changed: save=%d update=%d persist=%d", fs.saveCalls, fs.updateCalls, fs.persistCalls)
	}
}

func TestHandleResultDispatchV2PersistOnly(t *testing.T) {
	fs := &fakeV2AwareStore{}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: workerArticleResult("accepted", "正文")}
	if err := p.handleResultDispatch(dispatch); err != nil {
		t.Fatal(err)
	}
	if fs.persistCalls != 1 || fs.saveCalls != 0 || fs.updateCalls != 0 {
		t.Fatalf("v2 path: persist=%d save=%d update=%d", fs.persistCalls, fs.saveCalls, fs.updateCalls)
	}
	if len(p.taskStatuses) != 0 {
		t.Fatalf("v2 must not touch old task status maps")
	}
}

func TestHandleResultDispatchV2Replay(t *testing.T) {
	fs := &fakeV2AwareStore{
		persist: func(ctx context.Context, msg *protocol.ArticleResultV2) (store.PersistArticleResultV2Outcome, error) {
			return store.PersistArticleResultV2Outcome{TaskArticleID: 7, Replayed: true}, nil
		},
	}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: workerArticleResult("accepted", "正文")}
	if err := p.handleResultDispatch(dispatch); err != nil {
		t.Fatal(err)
	}
	if fs.saveCalls != 0 || fs.updateCalls != 0 {
		t.Fatalf("replay must not touch old storage")
	}
	if p.getOrCreateTaskStatus("task-v2").Stored != 0 {
		t.Fatalf("replay must not increment old Stored")
	}
}

func TestHandleResultDispatchV2Conflict(t *testing.T) {
	fs := &fakeV2AwareStore{
		persist: func(ctx context.Context, msg *protocol.ArticleResultV2) (store.PersistArticleResultV2Outcome, error) {
			return store.PersistArticleResultV2Outcome{}, store.ErrArticleResultConflict
		},
	}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: workerArticleResult("accepted", "正文")}
	err := p.handleResultDispatch(dispatch)
	if err == nil || !strings.Contains(err.Error(), store.ErrArticleResultConflict.Error()) {
		t.Fatalf("expected conflict error, got %v", err)
	}
	if fs.saveCalls != 0 || fs.updateCalls != 0 {
		t.Fatalf("conflict must not fall back to v1")
	}
}

func TestHandleResultDispatchV2PersistErrorNoFallback(t *testing.T) {
	fs := &fakeV2AwareStore{
		persist: func(ctx context.Context, msg *protocol.ArticleResultV2) (store.PersistArticleResultV2Outcome, error) {
			return store.PersistArticleResultV2Outcome{}, context.DeadlineExceeded
		},
	}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: workerArticleResult("accepted", "正文")}
	if err := p.handleResultDispatch(dispatch); err == nil {
		t.Fatal("expected persist error")
	}
	if fs.saveCalls != 0 || fs.updateCalls != 0 {
		t.Fatalf("v2 persist error must not call legacy storage")
	}
}

func TestHandleResultDispatchV2StoreUnsupported(t *testing.T) {
	fs := &fakeStore{}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: workerArticleResult("accepted", "正文")}
	err := p.handleResultDispatch(dispatch)
	if err == nil || !strings.Contains(err.Error(), "does not support ArticleResultV2") {
		t.Fatalf("expected unsupported store error, got %v", err)
	}
}

func TestHandleResultDispatchInvalidKindNoDefaultV1(t *testing.T) {
	fs := &fakeV2AwareStore{}
	p := newTestPool(fs)
	dispatch := &queue.ResultDispatch{Kind: 0, Message: legacyResultMessage()}
	if err := p.handleResultDispatch(dispatch); err == nil {
		t.Fatal("expected unknown kind error")
	}
	if fs.saveCalls != 0 || fs.persistCalls != 0 {
		t.Fatalf("invalid dispatch must not enter any path")
	}
}

func TestHandleResultDispatchV2PreservesAllStatuses(t *testing.T) {
	for _, status := range []string{"accepted", "review_required", "irrelevant", "extract_failed", "unsupported_format"} {
		fs := &fakeV2AwareStore{}
		p := newTestPool(fs)
		msg := workerArticleResult(status, "正文")
		if status == "extract_failed" || status == "unsupported_format" {
			msg = workerArticleResult(status, "")
		}
		dispatch := &queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: msg}
		if err := p.handleResultDispatch(dispatch); err != nil {
			t.Fatalf("%s: %v", status, err)
		}
		if fs.persistCalls != 1 || fs.saveCalls != 0 || fs.updateCalls != 0 {
			t.Fatalf("%s: persist=%d save=%d update=%d", status, fs.persistCalls, fs.saveCalls, fs.updateCalls)
		}
	}
}

func TestV2SameURLDifferentHitsNotDeduped(t *testing.T) {
	fs := &fakeV2AwareStore{}
	p := newTestPool(fs)
	first := workerArticleResult("accepted", "正文")
	second := workerArticleResult("accepted", "正文")
	second.HitID = "hit-v2-2"
	first.HitID = "hit-v2-1"
	_ = p.handleResultDispatch(&queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: first})
	_ = p.handleResultDispatch(&queue.ResultDispatch{Kind: queue.ResultDispatchV2, V2: second})
	if fs.persistCalls != 2 {
		t.Fatalf("same URL different hit_id must persist twice, got %d", fs.persistCalls)
	}
}

func TestStartResultConsumerUsesPopResultDispatch(t *testing.T) {
	data, err := os.ReadFile("pool.go")
	if err != nil {
		t.Fatal(err)
	}
	source := string(data)
	if !strings.Contains(source, "PopResultDispatch()") {
		t.Fatalf("StartResultConsumer must use PopResultDispatch")
	}
	if strings.Contains(source, "PopResultMessage()") {
		t.Fatalf("worker production consumer must not call PopResultMessage")
	}
}

func TestV2ConsumerDoesNotLogContent(t *testing.T) {
	data, err := os.ReadFile("pool.go")
	if err != nil {
		t.Fatal(err)
	}
	source := string(data)
	start := strings.Index(source, "func (p *Pool) consumeV2Result(")
	end := strings.Index(source, "func (p *Pool) getOrCreateTaskStatus(")
	if start < 0 || end < 0 || end < start {
		t.Fatalf("consumeV2Result function not found")
	}
	fn := source[start:end]
	if strings.Contains(fn, "msg.Content") || strings.Contains(fn, "RawMessage") || strings.Contains(fn, "ContentHash") {
		t.Fatalf("v2 consumer must not log content or raw JSON")
	}
}
