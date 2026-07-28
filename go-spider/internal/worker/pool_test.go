package worker

import (
	"errors"
	"strings"
	"testing"

	"crawler-platform/internal/protocol"
	"crawler-platform/internal/store"
)

type fakeStore struct {
	updateTask  func(id, status string, count int) error
	saveArticle func(article *store.Article) error
}

func (f *fakeStore) UpdateTask(id, status string, count int) error {
	if f.updateTask != nil {
		return f.updateTask(id, status, count)
	}
	return nil
}

func (f *fakeStore) SaveArticle(article *store.Article) error {
	if f.saveArticle != nil {
		return f.saveArticle(article)
	}
	return nil
}

var errUpdateFailed = errors.New("fake: update task failed")
var errSaveFailed = errors.New("fake: save article failed")

func newTestPool(store taskStore) *Pool {
	return &Pool{store: store, taskStatuses: make(map[string]*TaskStatus)}
}
func TestHandleSearchDone_CompletedSuccess(t *testing.T) {
	var gotID, gotStatus string
	var gotCount int
	store := &fakeStore{
		updateTask: func(id, status string, count int) error {
			gotID, gotStatus, gotCount = id, status, count
			return nil
		},
	}
	p := newTestPool(store)
	msg := &protocol.SearchDoneMessage{
		Envelope: protocol.Envelope{TaskID: "t1"},
		URLCount: 2,
	}
	p.getOrCreateTaskStatus("t1").Expected = 2
	p.getOrCreateTaskStatus("t1").Stored = 2

	err := p.handleSearchDone(msg)
	if err != nil {
		t.Fatalf("handleSearchDone returned error: %v", err)
	}
	if gotID != "t1" {
		t.Fatalf("got id %q, want t1", gotID)
	}
	if gotStatus != "completed" {
		t.Fatalf("got status %q, want completed", gotStatus)
	}
	if gotCount != 2 {
		t.Fatalf("got count %d, want 2", gotCount)
	}
}
func TestHandleSearchDone_CompletedWithErrorsSuccess(t *testing.T) {
	var gotStatus string
	store := &fakeStore{
		updateTask: func(id, status string, count int) error {
			gotStatus = status
			return nil
		},
	}
	p := newTestPool(store)
	msg := &protocol.SearchDoneMessage{
		Envelope: protocol.Envelope{TaskID: "t2"}, URLCount: 3,
	}
	ts := p.getOrCreateTaskStatus("t2")
	ts.Expected, ts.Stored, ts.Failed = 3, 2, 1

	err := p.handleSearchDone(msg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "completed_with_errors" {
		t.Fatalf("got %q, want completed_with_errors", gotStatus)
	}
}

func TestHandleSearchDone_FailedSuccess(t *testing.T) {
	var gotStatus string
	store := &fakeStore{
		updateTask: func(id, status string, count int) error {
			gotStatus = status
			return nil
		},
	}
	p := newTestPool(store)
	msg := &protocol.SearchDoneMessage{
		Envelope: protocol.Envelope{TaskID: "t3"}, URLCount: 2,
	}
	ts := p.getOrCreateTaskStatus("t3")
	ts.Expected, ts.Failed = 2, 2

	err := p.handleSearchDone(msg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "failed" {
		t.Fatalf("got %q, want failed", gotStatus)
	}
}

func TestHandleSearchDone_EmptySearch(t *testing.T) {
	var gotStatus string
	var gotCount int
	store := &fakeStore{
		updateTask: func(id, status string, count int) error {
			gotStatus, gotCount = status, count
			return nil
		},
	}
	p := newTestPool(store)
	msg := &protocol.SearchDoneMessage{
		Envelope: protocol.Envelope{TaskID: "t4"}, URLCount: 0,
	}
	err := p.handleSearchDone(msg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "completed" {
		t.Fatalf("got %q, want completed", gotStatus)
	}
	if gotCount != 0 {
		t.Fatalf("got count %d, want 0", gotCount)
	}
}

func TestHandleSearchDone_CompletedWriteFails(t *testing.T) {
	store := &fakeStore{updateTask: func(id, status string, count int) error { return errUpdateFailed }}
	p := newTestPool(store)
	p.getOrCreateTaskStatus("t5").Expected = 1
	p.getOrCreateTaskStatus("t5").Stored = 1
	msg := &protocol.SearchDoneMessage{
		Envelope: protocol.Envelope{TaskID: "t5"}, URLCount: 1,
	}
	err := p.handleSearchDone(msg)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, errUpdateFailed) {
		t.Fatalf("error should wrap sentinel, got: %v", err)
	}
}

func TestHandleSearchDone_CompletedWithErrorsWriteFails(t *testing.T) {
	store := &fakeStore{updateTask: func(id, status string, count int) error { return errUpdateFailed }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t6")
	ts.Expected, ts.Stored, ts.Failed = 3, 1, 2
	msg := &protocol.SearchDoneMessage{
		Envelope: protocol.Envelope{TaskID: "t6"}, URLCount: 3,
	}
	err := p.handleSearchDone(msg)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, errUpdateFailed) {
		t.Fatalf("error should wrap sentinel, got: %v", err)
	}
}

func TestHandleSearchDone_FailedWriteFails(t *testing.T) {
	store := &fakeStore{updateTask: func(id, status string, count int) error { return errUpdateFailed }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t7")
	ts.Expected, ts.Failed = 2, 2
	msg := &protocol.SearchDoneMessage{
		Envelope: protocol.Envelope{TaskID: "t7"}, URLCount: 2,
	}
	err := p.handleSearchDone(msg)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, errUpdateFailed) {
		t.Fatalf("error should wrap sentinel, got: %v", err)
	}
}

// checkTaskCompletion tests

func TestCheckTaskCompletion_NotReady(t *testing.T) {
	var called bool
	store := &fakeStore{updateTask: func(id, status string, count int) error { called = true; return nil }}
	p := newTestPool(store)
	p.getOrCreateTaskStatus("t8").Expected = 2
	_ = p.checkTaskCompletion("t8")
	if called {
		t.Fatal("UpdateTask should not be called when conditions not met")
	}
}
func TestCheckTaskCompletion_CompletedSuccess(t *testing.T) {
	var gotStatus string
	store := &fakeStore{updateTask: func(id, status string, count int) error { gotStatus = status; return nil }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t9")
	ts.SearchDone, ts.Expected, ts.Stored = true, 2, 2
	err := p.checkTaskCompletion("t9")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "completed" {
		t.Fatalf("got %q, want completed", gotStatus)
	}
}

func TestCheckTaskCompletion_CompletedWithErrorsSuccess(t *testing.T) {
	var gotStatus string
	store := &fakeStore{updateTask: func(id, status string, count int) error { gotStatus = status; return nil }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t10")
	ts.SearchDone, ts.Expected, ts.Stored, ts.Failed = true, 3, 2, 1
	err := p.checkTaskCompletion("t10")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "completed_with_errors" {
		t.Fatalf("got %q, want completed_with_errors", gotStatus)
	}
}

func TestCheckTaskCompletion_FailedSuccess(t *testing.T) {
	var gotStatus string
	store := &fakeStore{updateTask: func(id, status string, count int) error { gotStatus = status; return nil }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t11")
	ts.SearchDone, ts.Expected, ts.Failed = true, 2, 2
	err := p.checkTaskCompletion("t11")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "failed" {
		t.Fatalf("got %q, want failed", gotStatus)
	}
}

func TestCheckTaskCompletion_EmptyResult(t *testing.T) {
	var gotStatus string
	store := &fakeStore{updateTask: func(id, status string, count int) error { gotStatus = status; return nil }}
	p := newTestPool(store)
	p.getOrCreateTaskStatus("t12").SearchDone = true
	err := p.checkTaskCompletion("t12")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "completed" {
		t.Fatalf("got %q, want completed", gotStatus)
	}
}

func TestCheckTaskCompletion_WriteFails(t *testing.T) {
	store := &fakeStore{updateTask: func(id, status string, count int) error { return errUpdateFailed }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t13")
	ts.SearchDone, ts.Expected, ts.Stored = true, 1, 1
	err := p.checkTaskCompletion("t13")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, errUpdateFailed) {
		t.Fatalf("error should wrap sentinel, got: %v", err)
	}
}

// consumeResult tests

func TestConsumeResult_RunningUpdateFailsStillChecksCompletion(t *testing.T) {
	var runningCalled, completedCalled bool
	store := &fakeStore{
		saveArticle: func(a *store.Article) error { return nil },
		updateTask: func(id, status string, count int) error {
			if status == "running" {
				runningCalled = true
				return errUpdateFailed
			}
			if status == "completed" {
				completedCalled = true
			}
			return nil
		},
	}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t14")
	ts.SearchDone, ts.Expected = true, 1
	msg := &protocol.ResultMessage{
		Envelope: protocol.Envelope{TaskID: "t14"},
		URL:      "http://example.com/a", Site: "test", Keyword: "kw",
	}
	err := p.consumeResult(msg)
	if err != nil {
		t.Fatalf("error after running failure: %v", err)
	}
	if !runningCalled {
		t.Fatal("running UpdateTask should be called")
	}
	if !completedCalled {
		t.Fatal("completed checkTaskCompletion should still execute")
	}
}

func TestConsumeResult_SaveArticleFails(t *testing.T) {
	store := &fakeStore{saveArticle: func(a *store.Article) error { return errSaveFailed }}
	p := newTestPool(store)
	msg := &protocol.ResultMessage{
		Envelope: protocol.Envelope{TaskID: "t15"},
		URL:      "http://example.com/b",
	}
	err := p.consumeResult(msg)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, errSaveFailed) {
		t.Fatalf("should wrap sentinel, got: %v", err)
	}
}

func TestConsumeResult_DedupSkipped(t *testing.T) {
	var called bool
	store := &fakeStore{saveArticle: func(a *store.Article) error { called = true; return nil }}
	p := newTestPool(store)
	p.getOrCreateTaskStatus("t16").failedURLs = map[string]struct{}{"http://example.com/c": {}}
	msg := &protocol.ResultMessage{
		Envelope: protocol.Envelope{TaskID: "t16"},
		URL:      "http://example.com/c",
	}
	err := p.consumeResult(msg)
	if err != nil {
		t.Fatalf("error for dedup skip: %v", err)
	}
	if called {
		t.Fatal("SaveArticle should not be called for dedup URL")
	}
}

// consumeError tests

func TestConsumeError_SearchLevelWriteFails(t *testing.T) {
	store := &fakeStore{updateTask: func(id, status string, count int) error { return errUpdateFailed }}
	p := newTestPool(store)
	msg := &protocol.ErrorMessage{
		Envelope: protocol.Envelope{TaskID: "t17"},
		Stage:    "search", URL: "", Error: "connection timeout",
	}
	err := p.consumeError(msg)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "connection timeout") {
		t.Fatalf("must retain original search error, got: %v", err)
	}
	if !errors.Is(err, errUpdateFailed) {
		t.Fatalf("must wrap db sentinel, got: %v", err)
	}
}

func TestConsumeError_SearchLevelWriteSucceeds(t *testing.T) {
	var gotStatus string
	store := &fakeStore{updateTask: func(id, status string, count int) error { gotStatus = status; return nil }}
	p := newTestPool(store)
	msg := &protocol.ErrorMessage{
		Envelope: protocol.Envelope{TaskID: "t18"},
		Stage:    "search", URL: "", Error: "search failed",
	}
	err := p.consumeError(msg)
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if gotStatus != "failed" {
		t.Fatalf("got %q, want failed", gotStatus)
	}
}

func TestConsumeError_URLLevelCheckTaskCompletionFails(t *testing.T) {
	store := &fakeStore{updateTask: func(id, status string, count int) error { return errUpdateFailed }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t19")
	ts.SearchDone, ts.Expected = true, 1
	msg := &protocol.ErrorMessage{
		Envelope: protocol.Envelope{TaskID: "t19"},
		Stage:    "download", URL: "http://example.com/err",
	}
	err := p.consumeError(msg)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, errUpdateFailed) {
		t.Fatalf("should wrap sentinel, got: %v", err)
	}
}

func TestConsumeError_URLLevelDedupedSuccess(t *testing.T) {
	var updateCount int
	store := &fakeStore{updateTask: func(id, status string, count int) error { updateCount++; return nil }}
	p := newTestPool(store)
	ts := p.getOrCreateTaskStatus("t20")
	ts.SearchDone, ts.Expected = true, 1
	ts.storedURLs = map[string]struct{}{"http://example.com/dup": {}}
	msg := &protocol.ErrorMessage{
		Envelope: protocol.Envelope{TaskID: "t20"},
		Stage:    "download", URL: "http://example.com/dup",
	}
	err := p.consumeError(msg)
	if err != nil {
		t.Fatalf("should return nil for stored URL, got: %v", err)
	}
	if updateCount != 0 {
		t.Fatalf("UpdateTask called %d times, want 0", updateCount)
	}
}

// ---------------------------------------------------------------------------
// parsePublishTime
// ---------------------------------------------------------------------------

func TestParsePublishTime_DateOnly(t *testing.T) {
	pt, err := parsePublishTime("2026-07-27")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if pt == nil {
		t.Fatal("got nil, expected non-nil")
	}
	if pt.Year() != 2026 || pt.Month() != 7 || pt.Day() != 27 {
		t.Fatalf("got %d-%d-%d, want 2026-7-27", pt.Year(), pt.Month(), pt.Day())
	}
}

func TestParsePublishTime_RFC3339(t *testing.T) {
	pt, err := parsePublishTime("2026-07-27T16:00:00Z")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if pt == nil {
		t.Fatal("got nil")
	}
	if pt.Year() != 2026 || pt.Month() != 7 || pt.Day() != 27 {
		t.Fatalf("date mismatch")
	}
	if pt.Hour() != 16 || pt.Minute() != 0 {
		t.Fatalf("time mismatch")
	}
}

func TestParsePublishTime_Empty(t *testing.T) {
	pt, err := parsePublishTime("")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if pt != nil {
		t.Fatal("expected nil for empty string")
	}
}

func TestParsePublishTime_Whitespace(t *testing.T) {
	pt, err := parsePublishTime("  ")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if pt != nil {
		t.Fatal("expected nil for whitespace")
	}
}

func TestParsePublishTime_Invalid(t *testing.T) {
	pt, err := parsePublishTime("not-a-date")
	if err == nil {
		t.Fatal("expected error")
	}
	if pt != nil {
		t.Fatal("expected nil for invalid")
	}
}

// ---------------------------------------------------------------------------
// consumeResult publish_date scenarios
// ---------------------------------------------------------------------------

func TestConsumeResult_DateOnly(t *testing.T) {
	var captured *store.Article
	store := &fakeStore{
		saveArticle: func(a *store.Article) error { captured = a; return nil },
		updateTask:  func(id, status string, count int) error { return nil },
	}
	p := newTestPool(store)
	p.getOrCreateTaskStatus("t21").SearchDone = true
	p.getOrCreateTaskStatus("t21").Expected = 1

	msg := &protocol.ResultMessage{
		Envelope: protocol.Envelope{TaskID: "t21"},
		URL:      "http://example.com/art", Site: "test", Keyword: "kw",
		PublishDate: "2026-07-27", Title: "T", Content: "C", Score: 1,
	}
	_ = p.consumeResult(msg)
	if captured == nil {
		t.Fatal("SaveArticle not called")
	}
	if captured.PublishTime == nil {
		t.Fatal("PublishTime is nil")
	}
	if captured.PublishTime.Year() != 2026 || captured.PublishTime.Month() != 7 || captured.PublishTime.Day() != 27 {
		t.Fatalf("date mismatch: %v", captured.PublishTime)
	}
}

func TestConsumeResult_EmptyPublishDate(t *testing.T) {
	var captured *store.Article
	store := &fakeStore{
		saveArticle: func(a *store.Article) error { captured = a; return nil },
		updateTask:  func(id, status string, count int) error { return nil },
	}
	p := newTestPool(store)
	p.getOrCreateTaskStatus("t22").SearchDone = true
	p.getOrCreateTaskStatus("t22").Expected = 1

	msg := &protocol.ResultMessage{
		Envelope: protocol.Envelope{TaskID: "t22"},
		URL:      "http://example.com/art2", Site: "test", Keyword: "kw",
		PublishDate: "", Title: "T", Content: "C", Score: 1,
	}
	err := p.consumeResult(msg)
	if err != nil {
		t.Fatalf("consumeResult should not fail: %v", err)
	}
	if captured == nil {
		t.Fatal("SaveArticle not called")
	}
	if captured.PublishTime != nil {
		t.Fatal("PublishTime should be nil for empty publish_date")
	}
}

func TestConsumeResult_InvalidPublishDate(t *testing.T) {
	var captured *store.Article
	store := &fakeStore{
		saveArticle: func(a *store.Article) error { captured = a; return nil },
		updateTask:  func(id, status string, count int) error { return nil },
	}
	p := newTestPool(store)
	p.getOrCreateTaskStatus("t23").SearchDone = true
	p.getOrCreateTaskStatus("t23").Expected = 1

	msg := &protocol.ResultMessage{
		Envelope: protocol.Envelope{TaskID: "t23"},
		URL:      "http://example.com/art3", Site: "test", Keyword: "kw",
		PublishDate: "bad-date", Title: "T", Content: "C", Score: 1,
	}
	err := p.consumeResult(msg)
	if err != nil {
		t.Fatalf("invalid publish_date should not fail the whole result: %v", err)
	}
	if captured == nil {
		t.Fatal("SaveArticle not called")
	}
	if captured.PublishTime != nil {
		t.Fatal("PublishTime should be nil for bad date")
	}
	if captured.CrawlTime.IsZero() {
		t.Fatal("CrawlTime should be set")
	}
}
