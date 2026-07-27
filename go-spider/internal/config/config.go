package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// SiteConfig mirrors Python's site_cfg dict
type SiteConfig struct {
	Name      string       `json:"name"`
	Domain    string       `json:"domain"`
	BaseURL   string       `json:"base_url"`
	Search    SearchConfig `json:"search"`
	Extract   ExtractConfig `json:"extract"`
	Score     ScoreConfig  `json:"score"`
	RateLimit RateLimitConfig `json:"rate_limit"`
}

type SearchConfig struct {
	Type    string            `json:"type"`
	PageURL string            `json:"page_url"`
	APIURL  string            `json:"api_url"`
	Params  map[string]interface{} `json:"params"`
}

type ExtractConfig struct {
	Mode string `json:"mode"`
}

type ScoreConfig struct {
	TitleWeight int `json:"title_weight"`
	BodyWeight  int `json:"body_weight"`
	URLWeight   int `json:"url_weight"`
	Threshold   int `json:"threshold"`
}

type RateLimitConfig struct {
	Delay float64 `json:"delay"`
	Jitter float64 `json:"jitter"`
}

func Load(siteKey, configDir string) (*SiteConfig, error) {
	sitePath := filepath.Join(configDir, "site.json")
	httpPath := filepath.Join(configDir, "http.json")
	scorePath := filepath.Join(configDir, "score.json")

	sites := make(map[string]SiteConfig)
	if err := loadJSON(sitePath, &sites); err != nil {
		return nil, fmt.Errorf("site config: %w", err)
	}

	cfg, ok := sites[siteKey]
	if !ok {
		return nil, fmt.Errorf("site not found: %s", siteKey)
	}

	httpData := make(map[string]RateLimitConfig)
	if err := loadJSON(httpPath, &httpData); err == nil {
		if rl, ok := httpData[siteKey]; ok {
			cfg.RateLimit = rl
		}
	}

	scoreData := make(map[string]ScoreConfig)
	if err := loadJSON(scorePath, &scoreData); err == nil {
		if sc, ok := scoreData[siteKey]; ok {
			cfg.Score = sc
		} else if global, ok := scoreData["_global"]; ok {
			cfg.Score = global
		}
	}

	return &cfg, nil
}

func MustLoad(siteKey, configDir string) *SiteConfig {
	cfg, err := Load(siteKey, configDir)
	if err != nil {
		panic(err)
	}
	return cfg
}

func loadJSON(path string, v interface{}) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, v)
}
