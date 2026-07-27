package httpx

import (
	"log"
	"sync"
	"time"
)

type BreakerState int

const (
	Closed BreakerState = iota
	Open
	HalfOpen
)

func (s BreakerState) String() string {
	switch s {
	case Closed: return "CLOSED"
	case Open: return "OPEN"
	case HalfOpen: return "HALF_OPEN"
	default: return "UNKNOWN"
	}
}

type CircuitBreaker struct {
	mu               sync.Mutex
	name             string
	state            BreakerState
	failureCount     int
	failureThreshold int
	recoveryTimeout  time.Duration
	lastFailureTime  time.Time
}

func NewBreaker(name string, threshold int, recovery time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		name:             name,
		state:            Closed,
		failureThreshold: threshold,
		recoveryTimeout:  recovery,
	}
}

func (cb *CircuitBreaker) Allow() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	switch cb.state {
	case Closed:
		return true
	case Open:
		if time.Since(cb.lastFailureTime) >= cb.recoveryTimeout {
			cb.state = HalfOpen
			log.Printf("[breaker:%s] OPEN -> HALF_OPEN", cb.name)
			return true
		}
		return false
	case HalfOpen:
		return true
	}
	return false
}

func (cb *CircuitBreaker) Success() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.failureCount = 0
	if cb.state == HalfOpen {
		cb.state = Closed
		log.Printf("[breaker:%s] HALF_OPEN -> CLOSED", cb.name)
	}
}

func (cb *CircuitBreaker) Failure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.failureCount++
	cb.lastFailureTime = time.Now()
	if cb.failureCount >= cb.failureThreshold && cb.state != Open {
		cb.state = Open
		log.Printf("[breaker:%s] CLOSED -> OPEN (failures=%d)", cb.name, cb.failureCount)
	}
	if cb.state == HalfOpen {
		cb.state = Open
		log.Printf("[breaker:%s] HALF_OPEN -> OPEN", cb.name)
	}
}

func (cb *CircuitBreaker) State() BreakerState {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.state
}
