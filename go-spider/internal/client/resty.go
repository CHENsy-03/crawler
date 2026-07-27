package client

import (
	"encoding/json"
	"fmt"
	"log"
	"net/url"
	"strings"
	"time"

	"crawler-platform/internal/config"

	"github.com/go-resty/resty/v2"
)

type Article struct {
	Title string `json:"title"`
	URL   string `json:"url"`
}

type RestyFetcher struct {
	client *resty.Client
	delay  time.Duration
}

func NewRestyFetcher(delaySec float64) *RestyFetcher {
	c := resty.New().
		SetTimeout(15 * time.Second).
		SetRetryCount(3).
		SetRetryWaitTime(1 * time.Second).
		SetHeader("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36").
		SetHeader("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	return &RestyFetcher{client: c, delay: time.Duration(delaySec * float64(time.Second))}
}

func (f *RestyFetcher) Fetch(url string) (string, error) {
	if f.delay > 0 {
		time.Sleep(f.delay)
	}
	resp, err := f.client.R().Get(url)
	if err != nil {
		return "", fmt.Errorf("fetch %s: %w", url, err)
	}
	if resp.StatusCode() >= 400 {
		return "", fmt.Errorf("fetch %s: HTTP %d", url, resp.StatusCode())
	}
	return resp.String(), nil
}

func SearchArticles(cfg *config.SiteConfig, keyword string) []Article {
	search := cfg.Search
	if search.APIURL == "" {
		return nil
	}

	switch search.Type {
	case "trs_json":
		return searchTRS(cfg, keyword)
	case "jpaas_jsearch":
		return searchJPAAS(cfg, keyword)
	default:
		log.Printf("[client] unknown search type: %s", search.Type)
		return nil
	}
}

func searchTRS(cfg *config.SiteConfig, keyword string) []Article {
	params := map[string]string{}
	for k, v := range cfg.Search.Params {
		params[k] = fmt.Sprintf("%v", v)
	}
	params["qt"] = keyword
	params["pageSize"] = fmt.Sprintf("%v", cfg.Search.Params["pageSize"])
	params["page"] = "1"

	form := url.Values{}
	for k, v := range params {
		form.Set(k, v)
	}

	c := resty.New().SetTimeout(15 * time.Second)
	resp, err := c.R().
		SetHeader("Content-Type", "application/x-www-form-urlencoded").
		SetFormDataFromValues(form).
		Post(cfg.Search.APIURL)

	if err != nil {
		log.Printf("[trs] search error: %v", err)
		return nil
	}

	var result struct {
		ResultDocs []struct {
			Title   string `json:"title"`
			URL     string `json:"url"`
			Summary string `json:"summary"`
		} `json:"resultDocs"`
	}
	if err := json.Unmarshal(resp.Body(), &result); err != nil {
		log.Printf("[trs] parse error: %v", err)
		return nil
	}

	var articles []Article
	for _, doc := range result.ResultDocs {
		url := doc.URL
		if !strings.HasPrefix(url, "http") {
			url = cfg.BaseURL + url
		}
		articles = append(articles, Article{Title: doc.Title, URL: url})
	}
	log.Printf("[trs] %s -> %d results", keyword, len(articles))
	return articles
}

func searchJPAAS(cfg *config.SiteConfig, keyword string) []Article {
	params := map[string]string{
		"q":        keyword,
		"p":        "1",
		"pg":       "10",
		"sortType": "1",
	}
	for k, v := range cfg.Search.Params {
		params[k] = fmt.Sprintf("%v", v)
	}

	c := resty.New().SetTimeout(15 * time.Second)
	resp, err := c.R().
		SetHeader("X-Requested-With", "XMLHttpRequest").
		SetHeader("Accept", "*/*").
		SetQueryParams(params).
		Get(cfg.Search.APIURL)

	if err != nil {
		log.Printf("[jpaas] search error: %v", err)
		return nil
	}

	var result struct {
		Code string `json:"code"`
		Data struct {
			AppSearchResultBeanList []struct {
				MapSearchResult struct {
					Items []struct {
						Data struct {
							Title string `json:"title_str"`
							URL   string `json:"url"`
						} `json:"data"`
					} `json:"items"`
				} `json:"mapSearchResult"`
				Title string `json:"title_str"`
				URL   string `json:"url"`
			} `json:"appSearchResultBeanList"`
		} `json:"data"`
	}
	if err := json.Unmarshal(resp.Body(), &result); err != nil {
		log.Printf("[jpaas] parse error: %v", err)
		return nil
	}

	var articles []Article
	for _, doc := range result.Data.AppSearchResultBeanList {
		title := doc.Title
		articleURL := doc.URL
		if doc.MapSearchResult.Items != nil {
			for _, item := range doc.MapSearchResult.Items {
				if item.Data.Title != "" {
					title = item.Data.Title
				}
				if item.Data.URL != "" {
					articleURL = item.Data.URL
				}
			}
		}
		if articleURL == "" || title == "" {
			continue
		}
		if strings.HasPrefix(articleURL, "http://") {
			articleURL = strings.Replace(articleURL, "http://", "https://", 1)
		}
		articles = append(articles, Article{Title: title, URL: articleURL})
	}
	log.Printf("[jpaas] %s -> %d results", keyword, len(articles))
	return articles
}
