package security

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"
)

var v2NonIntegerPattern = regexp.MustCompile(`^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$`)

// EvidenceLimitsV2 is the OSEC-EVIDENCE-LIMITS-V2 frozen default set.
type EvidenceLimitsV2 struct {
	FileSize      int
	NestingDepth  int
	NumberDigits  int
	ArrayLength   int
	ObjectMembers int
	StringLength  int
	CaseCount     int
}

// DefaultEvidenceLimitsV2 returns the frozen V2 limits.
func DefaultEvidenceLimitsV2() EvidenceLimitsV2 {
	return EvidenceLimitsV2{
		FileSize:      16_777_216,
		NestingDepth:  128,
		NumberDigits:  4096,
		ArrayLength:   10_000,
		ObjectMembers: 1_000,
		StringLength:  1_048_576,
		CaseCount:     10_000,
	}
}

func v2NumberDigits(lexeme string) int {
	count := 0
	for _, r := range lexeme {
		if r >= '0' && r <= '9' {
			count++
		}
	}
	return count
}

func v2ValidNonInteger(raw string) bool {
	if !v2NonIntegerPattern.MatchString(raw) {
		return false
	}
	return strings.Contains(raw, ".") || strings.Contains(raw, "e") || strings.Contains(raw, "E")
}

func maxBridgeInt() int {
	return int(^uint(0) >> 1)
}

func applyV2Limits(value *Value, depth int, limits EvidenceLimitsV2) error {
	switch value.Kind {
	case NonIntegerKind:
		if v2NumberDigits(value.NonInteger) > limits.NumberDigits {
			return codeError("evidence_limit_number_digits")
		}
	case IntegerKind:
		if value.IntegerLexeme != "" && v2NumberDigits(strings.TrimPrefix(value.IntegerLexeme, "-")) > limits.NumberDigits {
			return codeError("evidence_limit_number_digits")
		}
	case StringKind:
		if len([]byte(value.String)) > limits.StringLength {
			return codeError("evidence_limit_string_length")
		}
	case ArrayKind:
		if depth > limits.NestingDepth {
			return codeError("evidence_limit_nesting_depth")
		}
		if len(value.Array) > limits.ArrayLength {
			return codeError("evidence_limit_array_length")
		}
		for i := range value.Array {
			if err := applyV2Limits(&value.Array[i], depth+1, limits); err != nil {
				return err
			}
		}
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
			if err := applyV2Limits(&value.Object[i].Value, depth+1, limits); err != nil {
				return err
			}
		}
	}
	return nil
}

// StrictDecodeV2 applies StrictDecode V1 syntax with EvidenceLimits V2 limits.
func StrictDecodeV2(raw []byte, limits EvidenceLimitsV2) (Value, error) {
	maxInt := maxBridgeInt()
	bridge := EvidenceLimits{
		FileSize:      limits.FileSize,
		NestingDepth:  maxInt,
		IntegerDigits: limits.NumberDigits,
		ArrayLength:   maxInt,
		ObjectMembers: maxInt,
		StringLength:  maxInt,
		CaseCount:     maxInt,
	}
	value, err := StrictDecode(raw, bridge)
	if err != nil {
		var evidenceErr *EvidenceError
		if errors.As(err, &evidenceErr) && evidenceErr.Code == "evidence_limit_integer_digits" {
			return Value{}, codeError("evidence_limit_number_digits")
		}
		return Value{}, err
	}
	if err := applyV2Limits(&value, 1, limits); err != nil {
		return Value{}, err
	}
	return value, nil
}

func validateV2Canonical(value Value) error {
	switch value.Kind {
	case NullKind, BoolKind:
		return nil
	case IntegerKind:
		if value.Integer == nil {
			return codeError("canonical_invalid_value_type")
		}
		if value.IntegerLexeme != "" && v2NumberDigits(strings.TrimPrefix(value.IntegerLexeme, "-")) > DefaultEvidenceLimitsV2().NumberDigits {
			return codeError("evidence_limit_number_digits")
		}
		return nil
	case NonIntegerKind:
		if !v2ValidNonInteger(value.NonInteger) {
			return codeError("canonical_invalid_number_lexeme")
		}
		if v2NumberDigits(value.NonInteger) > DefaultEvidenceLimitsV2().NumberDigits {
			return codeError("evidence_limit_number_digits")
		}
		return nil
	case StringKind:
		if !utf8.ValidString(value.String) {
			return codeError("canonical_invalid_unicode")
		}
		return nil
	case ArrayKind:
		for _, item := range value.Array {
			if err := validateV2Canonical(item); err != nil {
				return err
			}
		}
		return nil
	case ObjectKind:
		for _, member := range value.Object {
			if !utf8.ValidString(member.Key) {
				return codeError("canonical_invalid_unicode")
			}
			if err := validateV2Canonical(member.Value); err != nil {
				return err
			}
		}
		return nil
	default:
		return codeError("canonical_invalid_value_type")
	}
}

func encodeV2Canonical(buf *bytes.Buffer, value Value) error {
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
	case NonIntegerKind:
		buf.WriteString(value.NonInteger)
	case StringKind:
		return appendCanonicalString(buf, value.String)
	case ArrayKind:
		buf.WriteByte('[')
		for i, item := range value.Array {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := encodeV2Canonical(buf, item); err != nil {
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
			if err := encodeV2Canonical(buf, member.Value); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	default:
		return codeError("canonical_invalid_value_type")
	}
	return nil
}

// CanonicalJSONV2 implements OSEC-CANONICAL-JSON-V2.
func CanonicalJSONV2(value Value) ([]byte, error) {
	if err := validateV2Canonical(value); err != nil {
		return nil, err
	}
	var buf bytes.Buffer
	if err := encodeV2Canonical(&buf, value); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// CanonicalCaseV2 implements OSEC-CANONICAL-CASE-V2.
func CanonicalCaseV2(value Value) (CanonicalCaseResult, error) {
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
	canonical, err := CanonicalJSONV2(value)
	if err != nil {
		return CanonicalCaseResult{}, err
	}
	sum := sha256.Sum256(canonical)
	return CanonicalCaseResult{Canonical: canonical, SHA256: hex.EncodeToString(sum[:])}, nil
}
