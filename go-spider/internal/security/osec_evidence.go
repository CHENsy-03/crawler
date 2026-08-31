package security

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

const (
	aggregateV1MagicValue         = "OSEC-CASE-AGGREGATE-V1\x00"
	categoryAggregateV1MagicValue = "OSEC-CASE-CATEGORY-AGGREGATE-V1\x00"
	maxU32                        = uint64(0xFFFFFFFF)
)

var (
	caseIDPattern       = regexp.MustCompile(`^[a-z][a-z0-9-]{0,63}$`)
	categoryNamePattern = regexp.MustCompile(`^[a-z][a-z0-9_]{0,63}$`)
)

// ValueKind is the explicit OSEC typed AST kind.
type ValueKind int

const (
	NullKind ValueKind = iota
	BoolKind
	IntegerKind
	StringKind
	ArrayKind
	ObjectKind
	NonIntegerKind
)

// ObjectMember preserves decoded object key order and raw member count.
type ObjectMember struct {
	Key   string
	Value Value
}

// Value is the cross-language OSEC typed AST value.
type Value struct {
	Kind          ValueKind
	Bool          bool
	Integer       *big.Int
	IntegerLexeme string
	String        string
	Array         []Value
	Object        []ObjectMember
	NonInteger    string
}

// EvidenceLimits carries frozen OSEC-EVIDENCE-LIMITS-V1 values.
type EvidenceLimits struct {
	FileSize      int
	NestingDepth  int
	IntegerDigits int
	ArrayLength   int
	ObjectMembers int
	StringLength  int
	CaseCount     int
}

// DefaultEvidenceLimits returns the frozen default limits.
func DefaultEvidenceLimits() EvidenceLimits {
	return EvidenceLimits{
		FileSize:      16_777_216,
		NestingDepth:  128,
		IntegerDigits: 4096,
		ArrayLength:   10_000,
		ObjectMembers: 1_000,
		StringLength:  1_048_576,
		CaseCount:     10_000,
	}
}

// EvidenceError is the stable machine-code error.
type EvidenceError struct {
	Code    string
	Message string
}

func (e *EvidenceError) Error() string {
	return fmt.Sprintf("OSEC error %s: %s", e.Code, e.Message)
}

func codeError(code string) error {
	return &EvidenceError{Code: code, Message: code}
}

// CaseDigest is an id plus a 32-byte digest.
type CaseDigest struct {
	ID     string
	Digest []byte
}

// CanonicalCaseResult returns canonical bytes and digest.
type CanonicalCaseResult struct {
	Canonical []byte
	SHA256    string
}

func narrowSurrogatePrecheck(raw []byte) error {
	inString := false
	i := 0
	n := len(raw)
	for i < n {
		b := raw[i]
		if !inString {
			if b == '"' {
				inString = true
			}
			i++
			continue
		}
		if b == '\\' {
			if i+1 >= n {
				return fmt.Errorf("truncated escape")
			}
			next := raw[i+1]
			if next == 'u' {
				if i+6 > n {
					return fmt.Errorf("truncated unicode escape")
				}
				first, err := strconv.ParseUint(string(raw[i+2:i+6]), 16, 16)
				if err != nil {
					return err
				}
				if first >= 0xD800 && first <= 0xDBFF {
					if i+12 > n || raw[i+6] != '\\' || raw[i+7] != 'u' {
						return fmt.Errorf("lone high surrogate")
					}
					second, err := strconv.ParseUint(string(raw[i+8:i+12]), 16, 16)
					if err != nil || second < 0xDC00 || second > 0xDFFF {
						return fmt.Errorf("invalid surrogate pair")
					}
					i += 12
					continue
				}
				if first >= 0xDC00 && first <= 0xDFFF {
					return fmt.Errorf("lone low surrogate")
				}
				i += 6
				continue
			}
			i += 2
			continue
		}
		if b == '"' {
			inString = false
		}
		i++
	}
	return nil
}

func decodeValue(dec *json.Decoder) (Value, string, error) {
	tok, err := dec.Token()
	if err != nil {
		return Value{}, "", err
	}
	switch t := tok.(type) {
	case nil:
		return Value{Kind: NullKind}, "", nil
	case bool:
		return Value{Kind: BoolKind, Bool: t}, "", nil
	case string:
		return Value{Kind: StringKind, String: t}, "", nil
	case json.Number:
		lex := string(t)
		if strings.ContainsAny(lex, ".eE") {
			return Value{Kind: NonIntegerKind, NonInteger: lex}, "", nil
		}
		return Value{Kind: IntegerKind, IntegerLexeme: lex}, "", nil
	case json.Delim:
		switch t {
		case '[':
			var arr []Value
			dup := ""
			for dec.More() {
				item, nestedDup, err := decodeValue(dec)
				if err != nil {
					return Value{}, "", err
				}
				if dup == "" && nestedDup != "" {
					dup = nestedDup
				}
				arr = append(arr, item)
			}
			if _, err := dec.Token(); err != nil {
				return Value{}, "", err
			}
			return Value{Kind: ArrayKind, Array: arr}, dup, nil
		case '{':
			var members []ObjectMember
			seen := map[string]bool{}
			dup := ""
			for dec.More() {
				keyTok, err := dec.Token()
				if err != nil {
					return Value{}, "", err
				}
				key, ok := keyTok.(string)
				if !ok {
					return Value{}, "", fmt.Errorf("object key is not string")
				}
				if seen[key] && dup == "" {
					dup = key
				}
				seen[key] = true
				item, nestedDup, err := decodeValue(dec)
				if err != nil {
					return Value{}, "", err
				}
				if dup == "" && nestedDup != "" {
					dup = nestedDup
				}
				members = append(members, ObjectMember{Key: key, Value: item})
			}
			if _, err := dec.Token(); err != nil {
				return Value{}, "", err
			}
			return Value{Kind: ObjectKind, Object: members}, dup, nil
		}
	}
	return Value{}, "", fmt.Errorf("unknown JSON token")
}

// StrictDecode implements OSEC-STRICT-JSON-DECODE-V1.
func StrictDecode(raw []byte, limits EvidenceLimits) (Value, error) {
	if len(raw) > limits.FileSize {
		return Value{}, codeError("evidence_limit_file_size")
	}
	if bytes.HasPrefix(raw, []byte{0xEF, 0xBB, 0xBF}) {
		return Value{}, codeError("strict_decode_bom")
	}
	if !utf8.Valid(raw) {
		return Value{}, codeError("strict_decode_invalid_utf8")
	}
	trimmed := bytes.TrimLeft(raw, " \t\r\n")
	if len(trimmed) >= 2 && trimmed[0] == '0' && trimmed[1] >= '0' && trimmed[1] <= '9' {
		return Value{}, codeError("strict_decode_invalid_json")
	}
	if len(trimmed) >= 3 && trimmed[0] == '-' && trimmed[1] == '0' && trimmed[2] >= '0' && trimmed[2] <= '9' {
		return Value{}, codeError("strict_decode_invalid_json")
	}
	if numberPrefixEndsTruncated(trimmed) {
		return Value{}, codeError("strict_decode_invalid_json")
	}

	surrogateErr := narrowSurrogatePrecheck(raw)
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	value, dup, err := decodeValue(dec)
	if err != nil {
		return Value{}, codeError("strict_decode_invalid_json")
	}
	if _, err := dec.Token(); err != io.EOF {
		return Value{}, codeError("strict_decode_trailing_data")
	}
	if surrogateErr != nil {
		return Value{}, codeError("strict_decode_lone_surrogate")
	}
	if dup != "" {
		return Value{}, codeError("strict_decode_duplicate_key")
	}
	if err := applyLimits(&value, 1, limits); err != nil {
		return Value{}, err
	}
	return value, nil
}

func numberPrefixEndsTruncated(trimmed []byte) bool {
	i := 0
	n := len(trimmed)
	if i < n && trimmed[i] == '-' {
		i++
	}
	if i >= n {
		return false
	}
	if trimmed[i] == '0' {
		i++
	} else if trimmed[i] >= '1' && trimmed[i] <= '9' {
		for i < n && trimmed[i] >= '0' && trimmed[i] <= '9' {
			i++
		}
	} else {
		return false
	}
	if i < n && trimmed[i] == '.' {
		i++
		digits := 0
		for i < n && trimmed[i] >= '0' && trimmed[i] <= '9' {
			i++
			digits++
		}
		if digits == 0 {
			return true
		}
	}
	if i < n && (trimmed[i] == 'e' || trimmed[i] == 'E') {
		i++
		if i < n && (trimmed[i] == '+' || trimmed[i] == '-') {
			i++
		}
		digits := 0
		for i < n && trimmed[i] >= '0' && trimmed[i] <= '9' {
			i++
			digits++
		}
		if digits == 0 {
			return true
		}
	}
	return false
}

func applyLimits(value *Value, depth int, limits EvidenceLimits) error {
	switch value.Kind {
	case ObjectKind:
		if depth > limits.NestingDepth {
			return codeError("evidence_limit_nesting_depth")
		}
		if len(value.Object) > limits.ObjectMembers {
			return codeError("evidence_limit_object_members")
		}
		sort.SliceStable(value.Object, func(i, j int) bool {
			return bytes.Compare([]byte(value.Object[i].Key), []byte(value.Object[j].Key)) < 0
		})
		for i := range value.Object {
			if len([]byte(value.Object[i].Key)) > limits.StringLength {
				return codeError("evidence_limit_string_length")
			}
			if err := applyLimits(&value.Object[i].Value, depth+1, limits); err != nil {
				return err
			}
		}
	case ArrayKind:
		if depth > limits.NestingDepth {
			return codeError("evidence_limit_nesting_depth")
		}
		if len(value.Array) > limits.ArrayLength {
			return codeError("evidence_limit_array_length")
		}
		for i := range value.Array {
			if err := applyLimits(&value.Array[i], depth+1, limits); err != nil {
				return err
			}
		}
	case StringKind:
		if len([]byte(value.String)) > limits.StringLength {
			return codeError("evidence_limit_string_length")
		}
	case IntegerKind:
		digits := strings.TrimPrefix(value.IntegerLexeme, "-")
		if len(digits) > limits.IntegerDigits {
			return codeError("evidence_limit_integer_digits")
		}
		parsed, ok := new(big.Int).SetString(value.IntegerLexeme, 10)
		if !ok {
			return codeError("canonical_invalid_value_type")
		}
		value.Integer = parsed
	}
	return nil
}

func validateCanonicalValue(value Value) error {
	switch value.Kind {
	case NullKind, BoolKind:
		return nil
	case IntegerKind:
		if value.Integer == nil {
			return codeError("canonical_invalid_value_type")
		}
		return nil
	case NonIntegerKind:
		return codeError("canonical_non_integer_number")
	case StringKind:
		if !utf8.ValidString(value.String) {
			return codeError("canonical_invalid_unicode")
		}
		return nil
	case ArrayKind:
		for _, item := range value.Array {
			if err := validateCanonicalValue(item); err != nil {
				return err
			}
		}
		return nil
	case ObjectKind:
		for _, member := range value.Object {
			if !utf8.ValidString(member.Key) {
				return codeError("canonical_invalid_unicode")
			}
			if err := validateCanonicalValue(member.Value); err != nil {
				return err
			}
		}
		return nil
	default:
		return codeError("canonical_invalid_value_type")
	}
}

func appendCanonicalString(buf *bytes.Buffer, value string) error {
	if !utf8.ValidString(value) {
		return codeError("canonical_invalid_unicode")
	}
	buf.WriteByte('"')
	for _, r := range value {
		switch r {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\b':
			buf.WriteString(`\b`)
		case '\t':
			buf.WriteString(`\t`)
		case '\n':
			buf.WriteString(`\n`)
		case '\f':
			buf.WriteString(`\f`)
		case '\r':
			buf.WriteString(`\r`)
		default:
			if r < 0x20 {
				_, _ = fmt.Fprintf(buf, `\u%04x`, r)
			} else {
				buf.WriteRune(r)
			}
		}
	}
	buf.WriteByte('"')
	return nil
}

func encodeCanonicalValue(buf *bytes.Buffer, value Value) error {
	switch value.Kind {
	case NullKind:
		buf.WriteString("null")
	case BoolKind:
		if value.Bool {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case IntegerKind:
		buf.WriteString(value.Integer.String())
	case StringKind:
		return appendCanonicalString(buf, value.String)
	case ArrayKind:
		buf.WriteByte('[')
		for i, item := range value.Array {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := encodeCanonicalValue(buf, item); err != nil {
				return err
			}
		}
		buf.WriteByte(']')
	case ObjectKind:
		sorted := append([]ObjectMember(nil), value.Object...)
		sort.SliceStable(sorted, func(i, j int) bool {
			return bytes.Compare([]byte(sorted[i].Key), []byte(sorted[j].Key)) < 0
		})
		buf.WriteByte('{')
		for i, member := range sorted {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := appendCanonicalString(buf, member.Key); err != nil {
				return err
			}
			buf.WriteByte(':')
			if err := encodeCanonicalValue(buf, member.Value); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	default:
		return codeError("canonical_invalid_value_type")
	}
	return nil
}

// CanonicalJSON implements OSEC-CANONICAL-JSON-V1.
func CanonicalJSON(value Value) ([]byte, error) {
	if err := validateCanonicalValue(value); err != nil {
		return nil, err
	}
	var buf bytes.Buffer
	if err := encodeCanonicalValue(&buf, value); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// CanonicalCase implements OSEC-CANONICAL-CASE-V1.
func CanonicalCase(value Value) (CanonicalCaseResult, error) {
	if value.Kind != ObjectKind {
		return CanonicalCaseResult{}, codeError("canonical_root_not_object")
	}
	var idValue *Value
	for i := range value.Object {
		if value.Object[i].Key == "id" {
			idValue = &value.Object[i].Value
			break
		}
	}
	if idValue == nil {
		return CanonicalCaseResult{}, codeError("canonical_missing_id")
	}
	if idValue.Kind != StringKind || !caseIDPattern.MatchString(idValue.String) {
		return CanonicalCaseResult{}, codeError("canonical_invalid_id")
	}
	canonical, err := CanonicalJSON(value)
	if err != nil {
		return CanonicalCaseResult{}, err
	}
	sum := sha256.Sum256(canonical)
	return CanonicalCaseResult{Canonical: canonical, SHA256: hex.EncodeToString(sum[:])}, nil
}

// ValidateCaseDataset applies the dataset-level case_count limit before processing.
func ValidateCaseDataset(cases []Value, limits EvidenceLimits) (int, error) {
	count := len(cases)
	if count > limits.CaseCount {
		return count, codeError("evidence_limit_case_count")
	}
	return count, nil
}

func checkedU32(value uint64, code string) (uint32, error) {
	if value > maxU32 {
		return 0, codeError(code)
	}
	return uint32(value), nil
}

func aggregateRecords(magic string, prefix []byte, digests []CaseDigest) (string, error) {
	if len(digests) == 0 {
		return "", codeError("aggregate_empty_set")
	}
	seen := map[string]bool{}
	type record struct {
		id     []byte
		digest []byte
	}
	records := make([]record, 0, len(digests))
	for _, item := range digests {
		if seen[item.ID] {
			return "", codeError("aggregate_duplicate_id")
		}
		seen[item.ID] = true
		if len(item.Digest) != 32 {
			return "", codeError("aggregate_invalid_digest_length")
		}
		records = append(records, record{id: []byte(item.ID), digest: item.Digest})
	}
	sort.Slice(records, func(i, j int) bool {
		return bytes.Compare(records[i].id, records[j].id) < 0
	})
	count, err := checkedU32(uint64(len(records)), "aggregate_count_overflow")
	if err != nil {
		return "", err
	}
	stream := []byte(magic)
	stream = append(stream, prefix...)
	var countBytes [4]byte
	binary.BigEndian.PutUint32(countBytes[:], count)
	stream = append(stream, countBytes[:]...)
	for _, rec := range records {
		length, err := checkedU32(uint64(len(rec.id)), "aggregate_length_overflow")
		if err != nil {
			return "", err
		}
		var lengthBytes [4]byte
		binary.BigEndian.PutUint32(lengthBytes[:], length)
		stream = append(stream, lengthBytes[:]...)
		stream = append(stream, rec.id...)
		stream = append(stream, rec.digest...)
	}
	sum := sha256.Sum256(stream)
	return hex.EncodeToString(sum[:]), nil
}

// AggregateV1 implements OSEC-CASE-AGGREGATE-V1.
func AggregateV1(digests []CaseDigest, algorithm string) (string, error) {
	if algorithm != aggregateV1MagicValue[:len(aggregateV1MagicValue)-1] {
		return "", codeError("aggregate_unknown_algorithm")
	}
	return aggregateRecords(aggregateV1MagicValue, nil, digests)
}

// CategoryAggregateV1 implements OSEC-CASE-CATEGORY-AGGREGATE-V1.
func CategoryAggregateV1(categoryName string, digests []CaseDigest) (string, error) {
	if !categoryNamePattern.MatchString(categoryName) {
		return "", codeError("manifest_invalid_category")
	}
	encoded := []byte(categoryName)
	length, err := checkedU32(uint64(len(encoded)), "aggregate_length_overflow")
	if err != nil {
		return "", err
	}
	var lengthBytes [4]byte
	binary.BigEndian.PutUint32(lengthBytes[:], length)
	prefix := append(lengthBytes[:], encoded...)
	return aggregateRecords(categoryAggregateV1MagicValue, prefix, digests)
}
