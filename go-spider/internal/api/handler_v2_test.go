package api

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"crawler-platform/internal/worker"

	"github.com/gin-gonic/gin"
)

type fakeSearchPusher struct {
	v1Site    string
	v1Keyword string
	v2URL     string
	v2Words   []string
	err       error
	calls     chan string
}

func newFakeSearchPusher() *fakeSearchPusher {
	return &fakeSearchPusher{calls: make(chan string, 8)}
}

func (f *fakeSearchPusher) PushSearch(taskID, site, keyword string, level, maxPages int) error {
	f.v1Site = site
	f.v1Keyword = keyword
	f.calls <- "v1"
	return f.err
}

func (f *fakeSearchPusher) PushSearchRequested(taskID, targetURL string, keywords []string, level, maxPages int) error {
	f.v2URL = targetURL
	f.v2Words = keywords
	f.calls <- "v2"
	return f.err
}

func (f *fakeSearchPusher) waitCall(t *testing.T, want string) {
	t.Helper()
	select {
	case got := <-f.calls:
		if got != want {
			t.Fatalf("push call = %s, want %s", got, want)
		}
	case <-time.After(3 * time.Second):
		t.Fatalf("timed out waiting for %s push", want)
	}
}

func newCreateTaskServer(pusher searchPusher) *Server {
	gin.SetMode(gin.TestMode)
	s := &Server{
		router:  gin.New(),
		redis:   pusher,
		store:   NewTaskStore(),
		manager: worker.NewWorkerManager(1, nil, nil),
		db:      &fakeArticleQuerier{},
	}
	s.router.POST("/tasks", s.createTask)
	return s
}

func postJSON(t *testing.T, s *Server, payload map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	w := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "/tasks", bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	s.router.ServeHTTP(w, req)
	return w
}

func TestCreateTaskV1LegacyWithoutVersion(t *testing.T) {
	pusher := newFakeSearchPusher()
	s := newCreateTaskServer(pusher)
	w := postJSON(t, s, map[string]any{"site": "czj_beijing", "keywords": "低空经济", "max_pages": 1})
	if w.Code != 202 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp["protocol_version"] != "1.0" {
		t.Fatalf("protocol_version=%v", resp["protocol_version"])
	}
	pusher.waitCall(t, "v1")
	if pusher.v1Site != "czj_beijing" || pusher.v1Keyword != "低空经济" {
		t.Fatalf("v1 push = %s/%s", pusher.v1Site, pusher.v1Keyword)
	}
}

func TestCreateTaskV2Valid(t *testing.T) {
	pusher := newFakeSearchPusher()
	s := newCreateTaskServer(pusher)
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"target_url":       "https://example.gov.cn/search",
		"keywords":         []string{" 低空经济 ", "无人机", "低空经济", "   "},
		"max_pages":        5,
	})
	if w.Code != 202 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	pusher.waitCall(t, "v2")
	if pusher.v2URL != "https://example.gov.cn/search" {
		t.Fatalf("v2 url=%s", pusher.v2URL)
	}
	if len(pusher.v2Words) != 2 || pusher.v2Words[0] != "低空经济" || pusher.v2Words[1] != "无人机" {
		t.Fatalf("v2 keywords=%v", pusher.v2Words)
	}
}

func TestCreateTaskV2MissingVersion(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{"target_url": "https://example.gov.cn/search", "keywords": []string{"低空经济"}})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestCreateTaskUnknownVersion(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{"protocol_version": "9.9", "site": "czj_beijing", "keywords": "低空经济"})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestCreateTaskV2ConflictWithSite(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"site":             "czj_beijing",
		"target_url":       "https://example.gov.cn/search",
		"keywords":         []string{"低空经济"},
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestCreateTaskV1ConflictWithTargetURL(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "1.0",
		"site":             "czj_beijing",
		"keywords":         "低空经济",
		"target_url":       "https://example.gov.cn/search",
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestCreateTaskV2InvalidURL(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"target_url":       "ftp://example.gov.cn/search",
		"keywords":         []string{"低空经济"},
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestCreateTaskV2EmptyKeywords(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"target_url":       "https://example.gov.cn/search",
		"keywords":         []string{"", "   "},
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestCreateTaskV2ConflictWithKeyword(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"target_url":       "https://example.gov.cn/search",
		"keywords":         []string{"低空经济"},
		"keyword":          "低空经济",
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestCreateTaskV2ConflictWithProfile(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"target_url":       "https://example.gov.cn/search",
		"keywords":         []string{"低空经济"},
		"profile":          "czj_beijing",
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func errorBody(t *testing.T, w *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode error body: %v body=%s", err, w.Body.String())
	}
	return resp
}

func TestCreateTaskV1TargetURLWithoutSiteConflict(t *testing.T) {
	pusher := newFakeSearchPusher()
	s := newCreateTaskServer(pusher)
	w := postJSON(t, s, map[string]any{
		"protocol_version": "1.0",
		"keywords":         "低空经济",
		"target_url":       "https://example.gov.cn/search",
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	body := errorBody(t, w)
	if body["error"] == "" || !strings.Contains(body["error"].(string), "cannot be combined") {
		t.Fatalf("unexpected body: %v", body)
	}
	select {
	case call := <-pusher.calls:
		t.Fatalf("unexpected push: %s", call)
	default:
	}
}

func TestCreateTaskV1KeywordsArrayConflict(t *testing.T) {
	pusher := newFakeSearchPusher()
	s := newCreateTaskServer(pusher)
	w := postJSON(t, s, map[string]any{
		"protocol_version": "1.0",
		"site":             "czj_beijing",
		"keywords":         []string{"低空经济"},
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	body := errorBody(t, w)
	if body["error"] == "" || !strings.Contains(body["error"].(string), "cannot be combined") {
		t.Fatalf("unexpected body: %v", body)
	}
	select {
	case call := <-pusher.calls:
		t.Fatalf("unexpected push: %s", call)
	default:
	}
}

func TestCreateTaskMissingVersionV2KeywordsArray(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{"keywords": []string{"低空经济"}})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	body := errorBody(t, w)
	if body["error"] == "" || !strings.Contains(body["error"].(string), "protocol_version") {
		t.Fatalf("unexpected body: %v", body)
	}
}

func TestCreateTaskUnknownField(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"target_url":       "https://example.gov.cn/search",
		"keywords":         []string{"低空经济"},
		"bogus":            true,
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	body := errorBody(t, w)
	if body["error"] == "" || !strings.Contains(body["error"].(string), "unknown field") {
		t.Fatalf("unexpected body: %v", body)
	}
}

func TestCreateTaskV1ProfileCompatibility(t *testing.T) {
	pusher := newFakeSearchPusher()
	s := newCreateTaskServer(pusher)
	w := postJSON(t, s, map[string]any{
		"protocol_version": "1.0",
		"profile":          "czj_beijing",
		"keywords":         "低空经济",
	})
	if w.Code != 202 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	pusher.waitCall(t, "v1")
	if pusher.v1Site != "czj_beijing" {
		t.Fatalf("v1 site=%s", pusher.v1Site)
	}
}

func TestCreateTaskV1ConflictBody(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "1.0",
		"site":             "czj_beijing",
		"keywords":         "低空经济",
		"target_url":       "https://example.gov.cn/search",
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if body := errorBody(t, w); body["error"] == "" {
		t.Fatal("missing error body")
	}
}

func TestCreateTaskV2ConflictBody(t *testing.T) {
	s := newCreateTaskServer(newFakeSearchPusher())
	w := postJSON(t, s, map[string]any{
		"protocol_version": "2.0",
		"target_url":       "https://example.gov.cn/search",
		"keywords":         []string{"低空经济"},
		"keyword":          "低空经济",
	})
	if w.Code != 400 {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	if body := errorBody(t, w); body["error"] == "" {
		t.Fatal("missing error body")
	}
}

func postRawJSON(t *testing.T, s *Server, raw string) *httptest.ResponseRecorder {
	t.Helper()
	w := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "/tasks", bytes.NewReader([]byte(raw)))
	req.Header.Set("Content-Type", "application/json")
	s.router.ServeHTTP(w, req)
	return w
}

func TestCreateTaskV1SiteProfileMutuallyExclusive(t *testing.T) {
	for _, raw := range []string{
		`{"protocol_version":"1.0","site":"czj_beijing","profile":"other","keywords":"低空经济"}`,
		`{"protocol_version":"1.0","profile":"other","site":"czj_beijing","keywords":"低空经济"}`,
		`{"site":null,"profile":"","keywords":"低空经济"}`,
		`{"profile":"other","site":null,"keywords":"低空经济"}`,
	} {
		pusher := newFakeSearchPusher()
		s := newCreateTaskServer(pusher)
		w := postRawJSON(t, s, raw)
		if w.Code != 400 {
			t.Fatalf("status=%d body=%s raw=%s", w.Code, w.Body.String(), raw)
		}
		body := errorBody(t, w)
		if body["error"] != "site and profile are mutually exclusive" {
			t.Fatalf("unexpected body: %v raw=%s", body, raw)
		}
		select {
		case call := <-pusher.calls:
			t.Fatalf("unexpected push: %s raw=%s", call, raw)
		default:
		}
	}
}
