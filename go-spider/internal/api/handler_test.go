package api

import (
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"testing"

	"crawler-platform/internal/store"

	"github.com/gin-gonic/gin"
)

type fakeArticleQuerier struct {
	called   bool
	articles []store.Article
	err      error
}

func (f *fakeArticleQuerier) QueryArticles(keyword string, limit int) ([]store.Article, error) {
	f.called = true
	if f.err != nil {
		return nil, f.err
	}
	if keyword == "" {
		return f.articles, nil
	}
	var filtered []store.Article
	for _, a := range f.articles {
		if a.Keyword == keyword {
			filtered = append(filtered, a)
		}
	}
	return filtered, nil
}

func newTestServer(db articleQuerier) *Server {
	gin.SetMode(gin.TestMode)
	return &Server{router: gin.New(), db: db}
}

func setupRoutes(s *Server) {
	s.router.GET("/articles", s.listArticles)
}

func TestListArticles_ReturnsAll(t *testing.T) {
	db := &fakeArticleQuerier{
		articles: []store.Article{
			{URL: "http://example.com/1", Title: "A1", Score: 85, Site: "test", Keyword: "kw1"},
			{URL: "http://example.com/2", Title: "A2", Score: 90, Site: "test", Keyword: "kw2"},
		},
	}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("status=%d", w.Code)
	}
	var resp struct {
		Count    int
		Articles []store.Article
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Count != 2 {
		t.Fatalf("count=%d", resp.Count)
	}
	if resp.Articles[0].URL != "http://example.com/1" {
		t.Fatalf("url=%q", resp.Articles[0].URL)
	}
}

func TestListArticles_KeywordFilter(t *testing.T) {
	db := &fakeArticleQuerier{
		articles: []store.Article{
			{Title: "F", Keyword: "财政", Score: 10, URL: "http://a.com/f"},
			{Title: "T", Keyword: "科技", Score: 20, URL: "http://a.com/t"},
		},
	}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles?keyword=科技", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("status=%d", w.Code)
	}
	var resp struct {
		Count    int
		Articles []store.Article
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Count != 1 {
		t.Fatalf("count=%d", resp.Count)
	}
	if resp.Articles[0].Keyword != "科技" {
		t.Fatalf("keyword=%q", resp.Articles[0].Keyword)
	}
}

func TestListArticles_LimitParam(t *testing.T) {
	db := &fakeArticleQuerier{}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles?limit=10", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("status=%d", w.Code)
	}
	if !db.called {
		t.Fatal("QueryArticles should be called")
	}
}

func TestListArticles_EmptyResult(t *testing.T) {
	db := &fakeArticleQuerier{articles: []store.Article{}}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles", nil)
	s.router.ServeHTTP(w, req)
	var resp struct {
		Count    int
		Articles []store.Article
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Count != 0 {
		t.Fatalf("count=%d", resp.Count)
	}
	if resp.Articles == nil {
		t.Fatal("articles is null")
	}
}

func TestListArticles_NegativeLimit(t *testing.T) {
	db := &fakeArticleQuerier{articles: []store.Article{{Title: "x"}}}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles?limit=-1", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 400 {
		t.Fatalf("status=%d", w.Code)
	}
	if db.called {
		t.Fatal("QueryArticles should not be called for limit=-1")
	}
}

func TestListArticles_NonNumericLimit(t *testing.T) {
	db := &fakeArticleQuerier{articles: []store.Article{{Title: "x"}}}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles?limit=abc", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 400 {
		t.Fatalf("status=%d", w.Code)
	}
	if db.called {
		t.Fatal("QueryArticles should not be called for limit=abc")
	}
}

func TestListArticles_ZeroLimit(t *testing.T) {
	db := &fakeArticleQuerier{articles: []store.Article{{Title: "x"}}}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles?limit=0", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 400 {
		t.Fatalf("status=%d", w.Code)
	}
	if db.called {
		t.Fatal("QueryArticles should not be called for limit=0")
	}
}

func TestListArticles_ExceedsMaxLimit(t *testing.T) {
	db := &fakeArticleQuerier{articles: []store.Article{{Title: "x"}}}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles?limit=1001", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 400 {
		t.Fatalf("status=%d", w.Code)
	}
	if db.called {
		t.Fatal("QueryArticles should not be called for limit=1001")
	}
}

func TestListArticles_QueryError(t *testing.T) {
	db := &fakeArticleQuerier{err: fmt.Errorf("db error")}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 500 {
		t.Fatalf("status=%d", w.Code)
	}
	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["error"] == "" {
		t.Fatal("error field should be set")
	}
	if resp["error"] == "db error" {
		t.Fatal("must not leak internal error details")
	}
}

func TestListArticles_DefaultLimit(t *testing.T) {
	db := &fakeArticleQuerier{articles: make([]store.Article, 100)}
	s := newTestServer(db)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles", nil)
	s.router.ServeHTTP(w, req)
	var resp struct {
		Count int `json:"count"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Count != 100 {
		t.Fatalf("count=%d", resp.Count)
	}
}
func TestListArticles_DBNotAvailable(t *testing.T) {
	s := newTestServer(nil)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 503 { t.Fatalf("status=%d, want 503", w.Code) }
	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["error"] == "" { t.Fatal("error field should be set") }
	if resp["error"] == "db error" { t.Fatal("must not leak internal error details") }
}

func TestListArticles_TypedNilDBNotAvailable(t *testing.T) {
	var ms *store.MySQLStore
	s := newTestServer(ms)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 503 { t.Fatalf("status=%d, want 503", w.Code) }
	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["error"] == "" { t.Fatal("error field should be set") }
}

func TestListArticles_InvalidParamWhenDBNil(t *testing.T) {
	s := newTestServer(nil)
	setupRoutes(s)
	w := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/articles?limit=abc", nil)
	s.router.ServeHTTP(w, req)
	if w.Code != 400 { t.Fatalf("status=%d, want 400 (not 503)", w.Code) }
}
