package security

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"
)

func newTestCA(t *testing.T) (*x509.CertPool, *x509.Certificate, *ecdsa.PrivateKey) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("ca key: %v", err)
	}
	tmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "TASK022C Test CA"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatalf("ca cert: %v", err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatalf("parse ca: %v", err)
	}
	pool := x509.NewCertPool()
	pool.AddCert(cert)
	return pool, cert, key
}

func newTestServerCert(t *testing.T, ca *x509.Certificate, caKey *ecdsa.PrivateKey, dnsNames []string) tls.Certificate {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("server key: %v", err)
	}
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      pkix.Name{CommonName: dnsNames[0]},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:     dnsNames,
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, ca, &key.PublicKey, caKey)
	if err != nil {
		t.Fatalf("server cert: %v", err)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
}

func startTLSListener(t *testing.T, cert tls.Certificate, observedSNI *string, requests *[]string) (net.Listener, int) {
	t.Helper()
	raw, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	port := raw.Addr().(*net.TCPAddr).Port
	listener := tls.NewListener(raw, &tls.Config{Certificates: []tls.Certificate{cert}})
	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				tlsConn, ok := c.(*tls.Conn)
				if !ok {
					return
				}
				if err := tlsConn.Handshake(); err != nil {
					return
				}
				*observedSNI = tlsConn.ConnectionState().ServerName
				buf := make([]byte, 4096)
				n, _ := tlsConn.Read(buf)
				*requests = append(*requests, string(buf[:n]))
				_, _ = tlsConn.Write([]byte("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"))
			}(conn)
		}
	}()
	return listener, port
}

func TestPinnedTransportLocalHTTPSuccess(t *testing.T) {
	pool, ca, caKey := newTestCA(t)
	cert := newTestServerCert(t, ca, caKey, []string{"fixture.example"})
	var observedSNI string
	var requests []string
	listener, port := startTLSListener(t, cert, &observedSNI, &requests)
	defer listener.Close()

	target, err := newPinnedTargetForTest("https", "fixture.example", port, []string{"127.0.0.1"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	transport := NewPinnedTransport(target, nil, pool)
	req, _ := http.NewRequest(http.MethodGet, fmt.Sprintf("https://fixture.example:%d/", port), nil)
	resp, err := transport.RoundTrip(req)
	if err != nil {
		t.Fatalf("round trip: %v", err)
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode != 200 {
		t.Fatalf("status: %d", resp.StatusCode)
	}
	if observedSNI != "fixture.example" {
		t.Fatalf("SNI = %q", observedSNI)
	}
	if len(requests) != 1 || !strings.Contains(requests[0], fmt.Sprintf("Host: fixture.example:%d", port)) {
		t.Fatalf("host header missing: %v", requests)
	}
}

func TestPinnedTransportLocalHTTP(t *testing.T) {
	raw, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	port := raw.Addr().(*net.TCPAddr).Port
	requests := make(chan string, 1)
	go func() {
		defer raw.Close()
		conn, err := raw.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		buf := make([]byte, 4096)
		n, _ := conn.Read(buf)
		requests <- string(buf[:n])
		_, _ = conn.Write([]byte("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"))
	}()

	target, err := newPinnedTargetForTest("http", "fixture.example", port, []string{"127.0.0.1"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	transport := NewPinnedTransport(target, nil, nil)
	req, _ := http.NewRequest(http.MethodGet, fmt.Sprintf("http://fixture.example:%d/", port), nil)
	resp, err := transport.RoundTrip(req)
	if err != nil {
		t.Fatalf("round trip: %v", err)
	}
	_ = resp.Body.Close()
	request := <-requests
	if !strings.Contains(request, fmt.Sprintf("Host: fixture.example:%d", port)) {
		t.Fatalf("host header missing: %s", request)
	}
}

func TestPinnedTransportWrongSANFails(t *testing.T) {
	pool, ca, caKey := newTestCA(t)
	cert := newTestServerCert(t, ca, caKey, []string{"wrong.example"})
	var observedSNI string
	var requests []string
	listener, port := startTLSListener(t, cert, &observedSNI, &requests)
	defer listener.Close()

	target, err := newPinnedTargetForTest("https", "fixture.example", port, []string{"127.0.0.1"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	transport := NewPinnedTransport(target, nil, pool)
	req, _ := http.NewRequest(http.MethodGet, fmt.Sprintf("https://fixture.example:%d/", port), nil)
	_, err = transport.RoundTrip(req)
	if err == nil {
		t.Fatalf("expected hostname verification failure")
	}
}

func TestPinnedTransportUntrustedCAFails(t *testing.T) {
	_, ca, _ := newTestCA(t)
	_, otherCA, otherCAKey := newTestCA(t)
	cert := newTestServerCert(t, otherCA, otherCAKey, []string{"fixture.example"})
	clientPool := x509.NewCertPool()
	clientPool.AddCert(ca)
	var observedSNI string
	var requests []string
	listener, port := startTLSListener(t, cert, &observedSNI, &requests)
	defer listener.Close()

	target, err := newPinnedTargetForTest("https", "fixture.example", port, []string{"127.0.0.1"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	transport := NewPinnedTransport(target, nil, clientPool)
	req, _ := http.NewRequest(http.MethodGet, fmt.Sprintf("https://fixture.example:%d/", port), nil)
	_, err = transport.RoundTrip(req)
	if err == nil {
		t.Fatalf("expected untrusted CA failure")
	}
}

func TestPinnedTransportAuthorityMismatchNoDial(t *testing.T) {
	target, err := newPinnedTargetForTest("https", "fixture.example", 443, []string{"127.0.0.1"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	dialer := &recordingDialer{}
	transport := NewPinnedTransport(target, dialer.DialContext, nil)
	req, _ := http.NewRequest(http.MethodGet, "https://other.example/", nil)
	_, err = transport.RoundTrip(req)
	if err == nil || pinnedReason(err) != "authority_mismatch" {
		t.Fatalf("expected authority_mismatch, got %v", err)
	}
	if dialer.records != nil {
		t.Fatalf("dialer called after authority mismatch")
	}
}
