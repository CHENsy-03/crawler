package client

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFetchHTMLNoRedirectFinalURL(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte("<html><body>ok</body></html>"))
	}))
	defer server.Close()

	f := NewRestyFetcher(0)
	result, err := f.FetchHTML(server.URL)
	if err != nil {
		t.Fatalf("FetchHTML: %v", err)
	}
	if result.FinalURL != server.URL {
		t.Fatalf("FinalURL = %q, want %q", result.FinalURL, server.URL)
	}
	if result.ContentType != "text/html" {
		t.Fatalf("ContentType = %q, want text/html", result.ContentType)
	}
	if result.Body == "" {
		t.Fatal("Body is empty")
	}
}

func TestFetchHTMLRedirectFinalURL(t *testing.T) {
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/xhtml+xml; charset=utf-8")
		_, _ = w.Write([]byte("<html><body>final</body></html>"))
	}))
	defer target.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, target.URL, http.StatusFound)
	}))
	defer redirect.Close()

	f := NewRestyFetcher(0)
	result, err := f.FetchHTML(redirect.URL)
	if err != nil {
		t.Fatalf("FetchHTML redirect: %v", err)
	}
	if result.FinalURL != target.URL {
		t.Fatalf("FinalURL = %q, want %q", result.FinalURL, target.URL)
	}
	if result.ContentType != "application/xhtml+xml" {
		t.Fatalf("ContentType = %q, want application/xhtml+xml", result.ContentType)
	}
}

func TestFetchHTMLRejectsUnsupportedMIME(t *testing.T) {
	for _, contentType := range []string{"application/pdf", "application/msword", "application/json", ""} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if contentType != "" {
				w.Header().Set("Content-Type", contentType)
			}
			_, _ = w.Write([]byte("body"))
		}))
		_, err := NewRestyFetcher(0).FetchHTML(server.URL)
		server.Close()
		if err == nil {
			t.Fatalf("expected error for content type %q", contentType)
		}
		if !strings.Contains(err.Error(), "content type") {
			t.Fatalf("error = %v, want content type failure", err)
		}
	}
}

func TestFetchHTMLRejectsEmptyBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
	}))
	defer server.Close()

	_, err := NewRestyFetcher(0).FetchHTML(server.URL)
	if err == nil || !strings.Contains(err.Error(), "empty body") {
		t.Fatalf("err = %v, want empty body failure", err)
	}
}

func TestLegacyFetchStillReturnsBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte("<html>legacy</html>"))
	}))
	defer server.Close()

	body, err := NewRestyFetcher(0).Fetch(server.URL)
	if err != nil {
		t.Fatalf("legacy Fetch: %v", err)
	}
	if body != "<html>legacy</html>" {
		t.Fatalf("body = %q", body)
	}
}
