package worker

import (
	"errors"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"crawler-platform/internal/client"
	"crawler-platform/internal/protocol"
)

var (
	ErrV2DownloadFailed     = errors.New("v2 download failed")
	ErrV2UnsupportedHTML    = errors.New("v2 download is not supported HTML content")
	ErrV2EmptyHTMLBody      = errors.New("v2 download returned empty body")
	ErrV2CoordinatorStopped = errors.New("v2 download coordinator stopped")
)

type V2HTMLFetcher interface {
	FetchHTML(url string) (client.HTMLFetchResult, error)
}

type V2HTMLPublisher interface {
	PushHTMLMessageV2(msg *protocol.HTMLMessageV2) error
}

const (
	v2StatePending   = "pending"
	v2StateSucceeded = "succeeded"
	v2StateFailed    = "failed"
)

type v2DownloadState struct {
	cond       *sync.Cond
	status     string
	result     client.HTMLFetchResult
	err        error
	hits       map[string]*protocol.URLMessageV2
	published  map[string]bool
	publishing map[string]bool
	started    bool
}

type V2DownloadCoordinator struct {
	mu        sync.Mutex
	stopped   bool
	states    map[string]*v2DownloadState
	fetcher   V2HTMLFetcher
	publisher V2HTMLPublisher
	submitted atomic.Int64
	completed atomic.Int64
	failed    atomic.Int64
}

func NewV2DownloadCoordinator(fetcher V2HTMLFetcher, publisher V2HTMLPublisher) *V2DownloadCoordinator {
	return &V2DownloadCoordinator{
		states:    make(map[string]*v2DownloadState),
		fetcher:   fetcher,
		publisher: publisher,
	}
}

func (c *V2DownloadCoordinator) key(taskID, url string) string {
	return taskID + "\x00" + url
}

func (c *V2DownloadCoordinator) Stats() (submitted, completed, failed int64) {
	return c.submitted.Load(), c.completed.Load(), c.failed.Load()
}

func (c *V2DownloadCoordinator) Stop() {
	c.mu.Lock()
	c.stopped = true
	states := make([]*v2DownloadState, 0, len(c.states))
	for _, state := range c.states {
		state.status = v2StateFailed
		state.err = ErrV2CoordinatorStopped
		states = append(states, state)
	}
	c.states = make(map[string]*v2DownloadState)
	c.mu.Unlock()
	for _, state := range states {
		state.cond.Broadcast()
	}
}

func (c *V2DownloadCoordinator) Handle(msg *protocol.URLMessageV2) error {
	if err := msg.Validate(); err != nil {
		return err
	}
	key := c.key(msg.TaskID, msg.URL)

	c.mu.Lock()
	if c.stopped {
		c.mu.Unlock()
		return ErrV2CoordinatorStopped
	}
	state := c.states[key]
	if state == nil {
		state = &v2DownloadState{
			cond:       sync.NewCond(&c.mu),
			hits:       make(map[string]*protocol.URLMessageV2),
			published:  make(map[string]bool),
			publishing: make(map[string]bool),
		}
		c.states[key] = state
	}
	if state.published[msg.HitID] {
		c.mu.Unlock()
		return nil
	}
	state.hits[msg.HitID] = msg
	first := !state.started
	if first {
		state.started = true
		state.status = v2StatePending
		c.submitted.Add(1)
		go c.fetch(key, state, msg.URL)
	}
	for (state.status == v2StatePending || state.publishing[msg.HitID]) && !c.stopped {
		state.cond.Wait()
	}
	if c.stopped {
		c.mu.Unlock()
		return ErrV2CoordinatorStopped
	}
	status := state.status
	result := state.result
	downloadErr := state.err
	c.mu.Unlock()

	switch status {
	case v2StateSucceeded:
		return c.publishHit(state, msg, result)
	case v2StateFailed:
		if downloadErr == nil {
			downloadErr = ErrV2DownloadFailed
		}
		return downloadErr
	default:
		return fmt.Errorf("unknown v2 download state %q", status)
	}
}

func (c *V2DownloadCoordinator) fetch(key string, state *v2DownloadState, url string) {
	result, err := c.fetcher.FetchHTML(url)
	if err == nil {
		err = validateHTMLFetchResult(result)
	}

	c.mu.Lock()
	if c.stopped {
		state.status = v2StateFailed
		state.err = ErrV2CoordinatorStopped
		c.mu.Unlock()
		return
	}
	if err != nil {
		state.status = v2StateFailed
		state.err = err
		c.failed.Add(1)
	} else {
		state.status = v2StateSucceeded
		state.result = result
		c.completed.Add(1)
	}
	c.mu.Unlock()
	state.cond.Broadcast()

	if err == nil && !c.isStopped() {
		c.publishAllPending(state)
	}
}

func (c *V2DownloadCoordinator) isStopped() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.stopped
}

func validateHTMLFetchResult(result client.HTMLFetchResult) error {
	contentType := strings.ToLower(strings.TrimSpace(strings.SplitN(result.ContentType, ";", 2)[0]))
	if contentType != "text/html" && contentType != "application/xhtml+xml" {
		return fmt.Errorf("%w: %q", ErrV2UnsupportedHTML, result.ContentType)
	}
	if result.Body == "" {
		return ErrV2EmptyHTMLBody
	}
	return nil
}

func (c *V2DownloadCoordinator) publishAllPending(state *v2DownloadState) {
	c.mu.Lock()
	var hits []*protocol.URLMessageV2
	for _, hit := range state.hits {
		if !state.published[hit.HitID] && !state.publishing[hit.HitID] {
			hits = append(hits, hit)
		}
	}
	result := state.result
	c.mu.Unlock()

	for _, hit := range hits {
		_ = c.publishHit(state, hit, result)
	}
}

func (c *V2DownloadCoordinator) publishHit(state *v2DownloadState, hit *protocol.URLMessageV2, result client.HTMLFetchResult) error {
	c.mu.Lock()
	if c.stopped {
		c.mu.Unlock()
		return ErrV2CoordinatorStopped
	}
	if state.published[hit.HitID] {
		c.mu.Unlock()
		return nil
	}
	for state.publishing[hit.HitID] && !c.stopped {
		state.cond.Wait()
	}
	if state.published[hit.HitID] {
		c.mu.Unlock()
		return nil
	}
	if c.stopped {
		c.mu.Unlock()
		return ErrV2CoordinatorStopped
	}
	state.publishing[hit.HitID] = true
	c.mu.Unlock()

	msg := buildHTMLMessageV2(hit, result, time.Now().UTC())
	err := c.publisher.PushHTMLMessageV2(msg)

	c.mu.Lock()
	if err == nil {
		state.published[hit.HitID] = true
	}
	delete(state.publishing, hit.HitID)
	c.mu.Unlock()
	state.cond.Broadcast()
	return err
}

func buildHTMLMessageV2(hit *protocol.URLMessageV2, result client.HTMLFetchResult, now time.Time) *protocol.HTMLMessageV2 {
	return &protocol.HTMLMessageV2{
		ProtocolVersion: hit.ProtocolVersion,
		TaskID:          hit.TaskID,
		MessageID:       protocol.NewMessageID(),
		Timestamp:       now.Format(time.RFC3339),
		Type:            protocol.TypeHTMLV2,
		HitID:           hit.HitID,
		PlanID:          hit.PlanID,
		OriginalQuery:   hit.OriginalQuery,
		QueryTerm:       hit.QueryTerm,
		RequestedURL:    hit.URL,
		FinalURL:        result.FinalURL,
		ContentType:     result.ContentType,
		Title:           hit.Title,
		Snippet:         hit.Snippet,
		PublishedAt:     hit.PublishedAt,
		Source:          hit.Source,
		Level:           hit.Level,
		HTML:            result.Body,
	}
}
