package security

// BudgetError is a stable, sanitized budget/proxy policy failure.
type BudgetError struct {
	ReasonCode string
}

func (e *BudgetError) Error() string { return e.ReasonCode }

func budgetFail(reason string) error { return &BudgetError{ReasonCode: reason} }

const (
	DNSTimeoutMS            = 5000
	ConnectTimeoutMS        = 5000
	TLSTimeoutMS            = 5000
	ResponseHeaderTimeoutMS = 10000
	ReadIdleTimeoutMS       = 15000
	RequestBodyBytes        = 1048576
	ResponseHeadersBytes    = 262144
	MaxRedirects            = 3
	GlobalActive            = 20
	PerHostActive           = 5
	PerHostIdle             = 2
)

// TransportBudget is an immutable fixed budget model.
type TransportBudget struct {
	dnsTimeoutMS            int
	connectTimeoutMS        int
	tlsTimeoutMS            int
	responseHeaderTimeoutMS int
	readIdleTimeoutMS       int
	requestBodyBytes        int
	responseHeadersBytes    int
	maxRedirects            int
	globalActive            int
	perHostActive           int
	perHostIdle             int
}

// NewTransportBudget returns the fixed sealed budget.
func NewTransportBudget() TransportBudget {
	return TransportBudget{
		dnsTimeoutMS:            DNSTimeoutMS,
		connectTimeoutMS:        ConnectTimeoutMS,
		tlsTimeoutMS:            TLSTimeoutMS,
		responseHeaderTimeoutMS: ResponseHeaderTimeoutMS,
		readIdleTimeoutMS:       ReadIdleTimeoutMS,
		requestBodyBytes:        RequestBodyBytes,
		responseHeadersBytes:    ResponseHeadersBytes,
		maxRedirects:            MaxRedirects,
		globalActive:            GlobalActive,
		perHostActive:           PerHostActive,
		perHostIdle:             PerHostIdle,
	}
}

func (b TransportBudget) DNSTimeoutMS() int            { return b.dnsTimeoutMS }
func (b TransportBudget) ConnectTimeoutMS() int        { return b.connectTimeoutMS }
func (b TransportBudget) TLSTimeoutMS() int            { return b.tlsTimeoutMS }
func (b TransportBudget) ResponseHeaderTimeoutMS() int { return b.responseHeaderTimeoutMS }
func (b TransportBudget) ReadIdleTimeoutMS() int       { return b.readIdleTimeoutMS }
func (b TransportBudget) RequestBodyBytes() int        { return b.requestBodyBytes }
func (b TransportBudget) ResponseHeadersBytes() int    { return b.responseHeadersBytes }
func (b TransportBudget) MaxRedirects() int            { return b.maxRedirects }
func (b TransportBudget) GlobalActive() int            { return b.globalActive }
func (b TransportBudget) PerHostActive() int           { return b.perHostActive }
func (b TransportBudget) PerHostIdle() int             { return b.perHostIdle }

// BudgetProfile is an immutable request-class budget.
type BudgetProfile struct {
	name              string
	totalTimeoutMS    int
	responseBodyBytes int
}

func (p BudgetProfile) Name() string           { return p.name }
func (p BudgetProfile) TotalTimeoutMS() int    { return p.totalTimeoutMS }
func (p BudgetProfile) ResponseBodyBytes() int { return p.responseBodyBytes }

// BudgetForProfile returns the fixed profile for probe/search/detail.
func BudgetForProfile(name string) (BudgetProfile, error) {
	switch name {
	case "probe":
		return BudgetProfile{name: "probe", totalTimeoutMS: 30000, responseBodyBytes: 1048576}, nil
	case "search":
		return BudgetProfile{name: "search", totalTimeoutMS: 30000, responseBodyBytes: 8388608}, nil
	case "detail":
		return BudgetProfile{name: "detail", totalTimeoutMS: 60000, responseBodyBytes: 20971520}, nil
	default:
		return BudgetProfile{}, budgetFail("unknown_profile")
	}
}

func checkInt(value int) error {
	if value < 0 {
		return budgetFail("negative_budget")
	}
	return nil
}

// RemainingDeadline returns total - elapsed and rejects elapsed over budget.
func RemainingDeadline(profile BudgetProfile, elapsedMS int) (int, error) {
	if err := checkInt(elapsedMS); err != nil {
		return 0, err
	}
	if elapsedMS > profile.totalTimeoutMS {
		return 0, budgetFail("total_timeout_exceeded")
	}
	return profile.totalTimeoutMS - elapsedMS, nil
}

// CappedStageTimeout bounds a stage timeout by the remaining total deadline.
func CappedStageTimeout(profile BudgetProfile, stageTimeoutMS, elapsedMS int) (int, error) {
	if stageTimeoutMS <= 0 {
		return 0, budgetFail("non_positive_budget")
	}
	remaining, err := RemainingDeadline(profile, elapsedMS)
	if err != nil {
		return 0, err
	}
	if remaining <= 0 {
		return 0, budgetFail("total_timeout_exceeded")
	}
	if stageTimeoutMS < remaining {
		return stageTimeoutMS, nil
	}
	return remaining, nil
}

// CheckByteLimit accepts values up to limit inclusively.
func CheckByteLimit(value, limit int, reason string) error {
	if err := checkInt(value); err != nil {
		return err
	}
	if value > limit {
		return budgetFail(reason)
	}
	return nil
}

// CheckRequestBodyLimit validates the fixed request body budget.
func CheckRequestBodyLimit(value int) error {
	return CheckByteLimit(value, RequestBodyBytes, "request_body_limit")
}

// CheckResponseHeadersLimit validates the fixed response header budget.
func CheckResponseHeadersLimit(value int) error {
	return CheckByteLimit(value, ResponseHeadersBytes, "response_headers_limit")
}

// CheckResponseBodyLimit validates a profile response body budget.
func CheckResponseBodyLimit(profile BudgetProfile, value int) error {
	return CheckByteLimit(value, profile.responseBodyBytes, "response_body_limit")
}

// ValidateProxy rejects every non-empty proxy configuration.
func ValidateProxy(proxy string) error {
	if proxy == "" {
		return nil
	}
	return budgetFail("proxy_not_allowed")
}
