package protocol

const Version = "1.0"

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
}

type URLMessage struct {
	Envelope
	Type    string `json:"type"`
	URL     string `json:"url"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
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
	Type        string `json:"type"`
	URL         string `json:"url"`
	Title       string `json:"title"`
	PublishDate string `json:"publish_date"`
	Content     string `json:"content"`
	Score       int    `json:"score"`
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
