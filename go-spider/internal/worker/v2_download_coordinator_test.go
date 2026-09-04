package worker

import (
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"crawler-platform/internal/client"
	"crawler-platform/internal/protocol"
)

type fakeV2Fetcher struct {
	mu     sync.Mutex
	calls  int
	result client.HTMLFetchResult
	err    error
	delay  time.Duration
}

func (f *fakeV2Fetcher) FetchHTML(url string) (client.HTMLFetchResult, error) {
	f.mu.Lock()
	f.calls++
	f.mu.Unlock()
	if f.delay > 0 {
		time.Sleep(f.delay)
	}
	if f.err != nil {
		return client.HTMLFetchResult{}, f.err
	}
	return f.result, nil
}

func (f *fakeV2Fetcher) Count() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.calls
}

type fakeV2Publisher struct {
	mu       sync.Mutex
	messages []*protocol.HTMLMessageV2
	errByHit map[string]error
	calls    int
}

func (p *fakeV2Publisher) PushHTMLMessageV2(msg *protocol.HTMLMessageV2) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.calls++
	if err := p.errByHit[msg.HitID]; err != nil {
		return err
	}
	p.messages = append(p.messages, msg)
	return nil
}

func (p *fakeV2Publisher) Messages() []*protocol.HTMLMessageV2 {
	p.mu.Lock()
	defer p.mu.Unlock()
	out := append([]*protocol.HTMLMessageV2(nil), p.messages...)
	return out
}

func (p *fakeV2Publisher) Count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.calls
}

func v2URLMessage(hitID, taskID, url string) *protocol.URLMessageV2 {
	return &protocol.URLMessageV2{
		ProtocolVersion: protocol.VersionV2,
		TaskID:          taskID,
		MessageID:       "msg-" + hitID,
		Timestamp:       "2026-08-13T00:00:00Z",
		Type:            protocol.TypeURLV2,
		HitID:           hitID,
		PlanID:          "plan-1",
		OriginalQuery:   "k",
		QueryTerm:       "k",
		URL:             url,
		Title:           "T",
		Snippet:         "S",
		PublishedAt:     "2026-08-13",
		Source:          "example.gov.cn",
		Level:           0,
	}
}

func htmlResult() client.HTMLFetchResult {
	return client.HTMLFetchResult{
		Body:        "<html><body>ok</body></html>",
		FinalURL:    "https://example.gov.cn/a.html",
		ContentType: "text/html",
	}
}

func TestV2CoordinatorTwoHitsSameURLFetchOncePublishTwice(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult(), delay: 50 * time.Millisecond}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	var wg sync.WaitGroup
	for _, hit := range []string{"h1", "h2"} {
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			if err := coord.Handle(v2URLMessage(id, "task-a", "https://example.gov.cn/a.html")); err != nil {
				t.Errorf("Handle %s: %v", id, err)
			}
		}(hit)
	}
	wg.Wait()
	if fetcher.Count() != 1 {
		t.Fatalf("fetcher calls = %d, want 1", fetcher.Count())
	}
	messages := publisher.Messages()
	if len(messages) != 2 {
		t.Fatalf("messages = %d, want 2", len(messages))
	}
	if messages[0].HitID == messages[1].HitID {
		t.Fatal("hit ids should differ")
	}
	if messages[0].MessageID == messages[1].MessageID {
		t.Fatal("message ids should differ")
	}
}

func TestV2CoordinatorSecondHitAfterSuccessReusesResult(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult()}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	if err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html")); err != nil {
		t.Fatalf("first Handle: %v", err)
	}
	if err := coord.Handle(v2URLMessage("h2", "task-a", "https://example.gov.cn/a.html")); err != nil {
		t.Fatalf("second Handle: %v", err)
	}
	if fetcher.Count() != 1 {
		t.Fatalf("fetcher calls = %d, want 1", fetcher.Count())
	}
	if len(publisher.Messages()) != 2 {
		t.Fatalf("messages = %d, want 2", len(publisher.Messages()))
	}
}

func TestV2CoordinatorDuplicateHitPublishesOnce(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult()}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	msg := v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html")
	if err := coord.Handle(msg); err != nil {
		t.Fatalf("first Handle: %v", err)
	}
	if err := coord.Handle(msg); err != nil {
		t.Fatalf("duplicate Handle: %v", err)
	}
	if fetcher.Count() != 1 {
		t.Fatalf("fetcher calls = %d, want 1", fetcher.Count())
	}
	if len(publisher.Messages()) != 1 {
		t.Fatalf("messages = %d, want 1", len(publisher.Messages()))
	}
}

func TestV2CoordinatorDifferentTaskSameURLFetchesTwice(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult()}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	if err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html")); err != nil {
		t.Fatalf("task-a: %v", err)
	}
	if err := coord.Handle(v2URLMessage("h2", "task-b", "https://example.gov.cn/a.html")); err != nil {
		t.Fatalf("task-b: %v", err)
	}
	if fetcher.Count() != 2 {
		t.Fatalf("fetcher calls = %d, want 2", fetcher.Count())
	}
}

func TestV2CoordinatorSameTaskDifferentURLFetchesTwice(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult()}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	if err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html")); err != nil {
		t.Fatalf("first: %v", err)
	}
	if err := coord.Handle(v2URLMessage("h2", "task-a", "https://example.gov.cn/b.html")); err != nil {
		t.Fatalf("second: %v", err)
	}
	if fetcher.Count() != 2 {
		t.Fatalf("fetcher calls = %d, want 2", fetcher.Count())
	}
}

func TestV2CoordinatorDownloadFailureNoPublishNoRetry(t *testing.T) {
	fetcher := &fakeV2Fetcher{err: errors.New("boom")}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	if err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html")); err == nil {
		t.Fatal("expected download failure")
	}
	if err := coord.Handle(v2URLMessage("h2", "task-a", "https://example.gov.cn/a.html")); err == nil {
		t.Fatal("expected second hit failure")
	}
	if fetcher.Count() != 1 {
		t.Fatalf("fetcher calls = %d, want 1", fetcher.Count())
	}
	if len(publisher.Messages()) != 0 {
		t.Fatalf("messages = %d, want 0", len(publisher.Messages()))
	}
}

func TestV2CoordinatorUnsupportedMIMENoPublish(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: client.HTMLFetchResult{Body: "x", FinalURL: "https://example.gov.cn/a.html", ContentType: "application/pdf"}}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html"))
	if err == nil || !errors.Is(err, ErrV2UnsupportedHTML) {
		t.Fatalf("err = %v, want unsupported HTML", err)
	}
	if len(publisher.Messages()) != 0 {
		t.Fatalf("messages = %d, want 0", len(publisher.Messages()))
	}
}

func TestV2CoordinatorPublishFailureRetryAfterDuplicate(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult()}
	publisher := &fakeV2Publisher{errByHit: map[string]error{"h1": errors.New("push down")}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	if err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html")); err == nil {
		t.Fatal("expected publish failure")
	}
	if len(publisher.Messages()) != 0 {
		t.Fatalf("messages = %d, want 0", len(publisher.Messages()))
	}
	delete(publisher.errByHit, "h1")
	if err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html")); err != nil {
		t.Fatalf("retry Handle: %v", err)
	}
	if fetcher.Count() != 1 {
		t.Fatalf("fetcher calls = %d, want 1", fetcher.Count())
	}
	if len(publisher.Messages()) != 1 {
		t.Fatalf("messages = %d, want 1", len(publisher.Messages()))
	}
}

func TestV2CoordinatorConcurrentUniqueHits(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult(), delay: 10 * time.Millisecond}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			hit := "h" + string(rune('0'+n%10)) + string(rune('a'+n/10))
			if err := coord.Handle(v2URLMessage(hit, "task-a", "https://example.gov.cn/a.html")); err != nil {
				t.Errorf("Handle %s: %v", hit, err)
			}
		}(i)
	}
	wg.Wait()
	if fetcher.Count() != 1 {
		t.Fatalf("fetcher calls = %d, want 1", fetcher.Count())
	}
	messages := publisher.Messages()
	if len(messages) != 20 {
		t.Fatalf("messages = %d, want 20", len(messages))
	}
}

func TestV2CoordinatorStopReleasesAndRejects(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult()}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	coord := NewV2DownloadCoordinator(fetcher, publisher)
	coord.Stop()
	err := coord.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html"))
	if err == nil || !strings.Contains(err.Error(), "stopped") {
		t.Fatalf("err = %v, want stopped", err)
	}
	if fetcher.Count() != 0 {
		t.Fatalf("fetcher calls = %d, want 0", fetcher.Count())
	}
}

func TestPoolStopReleasesV2Coordinator(t *testing.T) {
	fetcher := &fakeV2Fetcher{result: htmlResult()}
	publisher := &fakeV2Publisher{errByHit: map[string]error{}}
	pool := NewPool(1, nil, nil)
	pool.v2 = NewV2DownloadCoordinator(fetcher, publisher)
	pool.Stop()
	err := pool.v2.Handle(v2URLMessage("h1", "task-a", "https://example.gov.cn/a.html"))
	if err == nil || !strings.Contains(err.Error(), "stopped") {
		t.Fatalf("err = %v, want stopped", err)
	}
	if fetcher.Count() != 0 {
		t.Fatalf("fetcher calls = %d, want 0", fetcher.Count())
	}
}
