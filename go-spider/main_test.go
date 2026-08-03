package main

import (
	"strings"
	"testing"

	"crawler-platform/internal/queue"
)

func TestPrepareCLIInputV1(t *testing.T) {
	in, err := prepareCLIInput("czj_beijing", "", " 低空经济 ")
	if err != nil || in.mode != "v1" {
		t.Fatalf("mode=%v err=%v", in, err)
	}
	if in.keywords != "低空经济" {
		t.Fatalf("keywords=%q", in.keywords)
	}
}

func TestPrepareCLIInputV2(t *testing.T) {
	in, err := prepareCLIInput("", "https://example.gov.cn/search", " 低空经济 ,无人机,低空经济,  ")
	if err != nil || in.mode != "v2" {
		t.Fatalf("mode=%v err=%v", in, err)
	}
	want := []string{"低空经济", "无人机"}
	if len(in.normalizedKeywords) != 2 || in.normalizedKeywords[0] != want[0] || in.normalizedKeywords[1] != want[1] {
		t.Fatalf("keywords=%v", in.normalizedKeywords)
	}
}

func TestPrepareCLIInputMutuallyExclusive(t *testing.T) {
	if _, err := prepareCLIInput("czj_beijing", "https://example.gov.cn/search", "低空经济"); err == nil {
		t.Fatal("expected mutual exclusion error")
	}
}

func TestPrepareCLIInputRequiresMode(t *testing.T) {
	if _, err := prepareCLIInput("", "", "低空经济"); err == nil {
		t.Fatal("expected mode required error")
	}
}

func TestPrepareCLIInputRejectsBlankV1Keywords(t *testing.T) {
	for _, keywords := range []string{"", "   "} {
		if _, err := prepareCLIInput("czj_beijing", "", keywords); err == nil {
			t.Fatalf("expected blank v1 keyword error for %q", keywords)
		}
	}
}

func TestPrepareCLIInputRejectsBlankV2Keywords(t *testing.T) {
	for _, keywords := range []string{"", " ", ", ,"} {
		if _, err := prepareCLIInput("", "https://example.gov.cn/search", keywords); err == nil {
			t.Fatalf("expected blank v2 keyword error for %q", keywords)
		}
	}
}

func TestPrepareCLIInputRejectsInvalidURL(t *testing.T) {
	for _, url := range []string{"ftp://example.gov.cn", "/relative", " https://example.gov.cn", "https://example.gov.cn:abc"} {
		if _, err := prepareCLIInput("", url, "低空经济"); err == nil {
			t.Fatalf("expected invalid url error for %q", url)
		}
	}
}

func TestPrepareCLIInputReturnsCleanV1Keywords(t *testing.T) {
	in, err := prepareCLIInput("czj_beijing", "", "低空经济,无人机")
	if err != nil {
		t.Fatal(err)
	}
	if in.keywords != "低空经济,无人机" {
		t.Fatalf("v1 multi-keyword string changed: %q", in.keywords)
	}
}

func TestRunCLIInputFailureBeforeRedisFactory(t *testing.T) {
	cases := []struct {
		name            string
		site, url, kw   string
		wantErrFragment string
	}{
		{"v1 blank keywords", "czj_beijing", "", "   ", "must not be blank"},
		{"v2 blank keywords", "", "https://example.gov.cn", " , ", "at least one non-blank keyword"},
		{"invalid url", "", "ftp://example.gov.cn", "低空经济", "must use http or https"},
		{"mutually exclusive", "czj_beijing", "https://example.gov.cn", "低空经济", "--url and --site are mutually exclusive"},
		{"missing entry", "", "", "低空经济", "either --site or --url is required"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			err := runCLI(tc.site, tc.url, tc.kw, "unused", 1, 1, func(string) *queue.RedisQueue {
				calls++
				return nil
			}, nil)
			if err == nil {
				t.Fatal("expected input error")
			}
			if !strings.Contains(err.Error(), tc.wantErrFragment) {
				t.Fatalf("error %q does not contain %q", err.Error(), tc.wantErrFragment)
			}
			if calls != 0 {
				t.Fatalf("redis factory called %d times before input validation", calls)
			}
		})
	}
}
