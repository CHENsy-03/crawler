package protocol

import (
	"crypto/rand"
	"fmt"
)

const Version = "1.0"

func NewTaskID() string {
	b := make([]byte, 4)
	rand.Read(b)
	return fmt.Sprintf("task-%x", b)
}

func NewMessageID() string {
	b := make([]byte, 4)
	rand.Read(b)
	return fmt.Sprintf("msg-%x", b)
}

type Envelope struct {
	ProtocolVersion string `json:"protocol_version"`
	TaskID          string `json:"task_id"`
	MessageID       string `json:"message_id"`
	Timestamp       string `json:"timestamp"`
}

type SearchMessage struct {
	Envelope
	Type    string `json:"type"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
	MaxPages int    `json:"max_pages"`
}

type URLMessage struct {
	Envelope
	Type    string `json:"type"`
	URL     string `json:"url"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
	Title   string `json:"title"`
}

type HTMLMessage struct {
	Envelope
	Type    string `json:"type"`
	URL     string `json:"url"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
	Title   string `json:"title"`
	HTML    string `json:"html"`
}

type ResultMessage struct {
	Envelope
	Type        string   `json:"type"`
	Site        string   `json:"site"`
	Keyword     string   `json:"keyword"`
	Level       int      `json:"level"`
	URL         string   `json:"url"`
	Title       string   `json:"title"`
	PublishDate string   `json:"publish_date"`
	Content     string   `json:"content"`
	Summary     string   `json:"summary"`
	Score       int      `json:"score"`
	MatchedKeywords []string `json:"matched_keywords"`
}

type SearchDoneMessage struct {
	Envelope
	Type     string `json:"type"`
	Site     string `json:"site"`
	Keyword  string `json:"keyword"`
	URLCount int    `json:"url_count"`
	Level    int    `json:"level"`
}

type ErrorMessage struct {
	Envelope
	Type      string `json:"type"`
	Stage     string `json:"stage"`
	URL       string `json:"url"`
	ErrorCode string `json:"error_code"`
	Error     string `json:"error"`
	Retryable bool   `json:"retryable"`
}
