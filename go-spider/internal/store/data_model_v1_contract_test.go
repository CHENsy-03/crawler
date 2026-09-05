package store

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"strings"
	"testing"
)

type dataModelFixture struct {
	ContractVersion         string            `json:"contract_version"`
	V10Entities             []string          `json:"v1_0_entities"`
	V11AddedEntities        []string          `json:"v1_1_added_entities"`
	Entities                []string          `json:"entities"`
	Tables                  []string          `json:"tables"`
	PrimaryKeys             map[string]string `json:"primary_keys"`
	ULIDEntities            []string          `json:"ulid_entities"`
	AuditLogExceptionEntity string            `json:"audit_log_exception_entity"`
	PrimaryKeyType          string            `json:"primary_key_type"`
	AuditLogPrimaryKeyType  string            `json:"audit_log_primary_key_type"`
	SamplePrimaryKeys       map[string]string `json:"sample_primary_keys"`
}

func loadDataModelFixture(t *testing.T) dataModelFixture {
	t.Helper()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "data_model_22_entities.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var fixture dataModelFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	return fixture
}

func readMigrationFile(t *testing.T, name string) string {
	t.Helper()
	path := filepath.Join("..", "..", "..", "migrations", "mysql", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read migration %s: %v", name, err)
	}
	return string(data)
}

func tableSegment(t *testing.T, ddl, table string) string {
	t.Helper()
	pattern := regexp.MustCompile(`(?s)CREATE TABLE ` + regexp.QuoteMeta(table) + ` \((.*?)\n\) ENGINE=InnoDB`)
	match := pattern.FindStringSubmatch(ddl)
	if len(match) != 2 {
		t.Fatalf("table segment not found: %s", table)
	}
	return match[1]
}

type ddlColumn struct {
	Name string
	Type string
	Null bool
}

func parseDDLColumns(t *testing.T, ddl, table string) []ddlColumn {
	t.Helper()
	segment := tableSegment(t, ddl, table)
	var out []ddlColumn
	for _, raw := range strings.Split(segment, "\n") {
		line := strings.TrimSpace(raw)
		if line == "" {
			continue
		}
		if strings.HasPrefix(line, "PRIMARY KEY") || strings.HasPrefix(line, "UNIQUE KEY") || strings.HasPrefix(line, "KEY ") || strings.HasPrefix(line, "CONSTRAINT ") {
			continue
		}
		parts := strings.SplitN(line, " ", 2)
		if len(parts) != 2 {
			continue
		}
		name := strings.TrimSpace(parts[0])
		definition := strings.TrimSuffix(strings.TrimSpace(parts[1]), ",")
		typeText := strings.ToUpper(definition)
		for _, marker := range []string{" NOT NULL", " GENERATED", " DEFAULT ", " NULL", " PRIMARY KEY"} {
			if idx := strings.Index(typeText, marker); idx >= 0 {
				typeText = typeText[:idx]
				break
			}
		}
		typeText = strings.Join(strings.Fields(typeText), " ")
		notNull := strings.Contains(strings.ToUpper(definition), " NOT NULL")
		out = append(out, ddlColumn{Name: name, Type: typeText, Null: !notNull})
	}
	return out
}

func gormColumnType(tag string) string {
	parts := strings.Split(tag, ";")
	for _, part := range parts {
		if strings.HasPrefix(part, "type:") {
			return strings.Join(strings.Fields(strings.ToUpper(strings.TrimPrefix(part, "type:"))), " ")
		}
	}
	return ""
}

func gormColumnName(tag string) string {
	parts := strings.Split(tag, ";")
	for _, part := range parts {
		if strings.HasPrefix(part, "column:") {
			return strings.TrimPrefix(part, "column:")
		}
	}
	return ""
}

func hasGormFlag(tag, flag string) bool {
	parts := strings.Split(tag, ";")
	for _, part := range parts {
		if part == flag {
			return true
		}
	}
	return false
}

func modelColumns(t *testing.T, model any) []ddlColumn {
	t.Helper()
	typ := reflect.TypeOf(model)
	if typ.Kind() == reflect.Pointer {
		typ = typ.Elem()
	}
	if typ.Kind() != reflect.Struct {
		t.Fatalf("model is not struct: %T", model)
	}
	var out []ddlColumn
	for i := 0; i < typ.NumField(); i++ {
		field := typ.Field(i)
		tag := field.Tag.Get("gorm")
		if tag == "" || strings.Contains(tag, "-") && !strings.Contains(tag, "->:false") {
			continue
		}
		if !strings.Contains(tag, "column:") {
			continue
		}
		notNull := hasGormFlag(tag, "not null")
		out = append(out, ddlColumn{
			Name: gormColumnName(tag),
			Type: gormColumnType(tag),
			Null: !notNull,
		})
	}
	return out
}

func TestDataModelV1HasExactly22Entities(t *testing.T) {
	fixture := loadDataModelFixture(t)
	if len(fixture.Entities) != 22 {
		t.Fatalf("fixture entity count %d", len(fixture.Entities))
	}
	if len(fixture.V10Entities) != 21 {
		t.Fatalf("v1.0 entity count %d", len(fixture.V10Entities))
	}
	if len(fixture.V11AddedEntities) != 1 || fixture.V11AddedEntities[0] != "GlobalBlockEntry" {
		t.Fatalf("v1.1 addition mismatch")
	}
	model := DataModelV1EntityNames()
	if len(model) != 22 {
		t.Fatalf("go model count %d", len(model))
	}
	for i := range fixture.Entities {
		if model[i] != fixture.Entities[i] {
			t.Fatalf("entity order mismatch %d %s vs %s", i, model[i], fixture.Entities[i])
		}
	}
	if len(DataModelV1FormalModels()) != 22 {
		t.Fatalf("formal model count %d", len(DataModelV1FormalModels()))
	}
}

func TestDataModelV1FixtureULIDsAreCanonical(t *testing.T) {
	fixture := loadDataModelFixture(t)
	for _, entity := range fixture.ULIDEntities {
		id, ok := fixture.SamplePrimaryKeys[entity]
		if !ok {
			t.Fatalf("fixture missing sample ULID for %s", entity)
		}
		if !IsCanonicalULIDV1(id) {
			t.Fatalf("fixture sample is not canonical ULID: %s=%s", entity, id)
		}
	}
	if len(fixture.ULIDEntities) != 21 {
		t.Fatalf("ulid entity count %d", len(fixture.ULIDEntities))
	}
	if fixture.AuditLogExceptionEntity != "AuditLog" {
		t.Fatalf("audit exception mismatch")
	}
	models := DataModelV1Entities()
	for _, entity := range models {
		if fixture.PrimaryKeys[entity.Name] != entity.Primary {
			t.Fatalf("primary key mismatch for %s: fixture=%s model=%s", entity.Name, fixture.PrimaryKeys[entity.Name], entity.Primary)
		}
	}
}

func TestDataModelV1FormalModelsAreNotMetadataOnly(t *testing.T) {
	fixture := loadDataModelFixture(t)
	models := DataModelV1FormalModels()
	if len(models) != 22 {
		t.Fatalf("formal model count %d", len(models))
	}
	seenTables := map[string]bool{}
	for _, model := range models {
		typ := reflect.TypeOf(model)
		if typ.Kind() != reflect.Pointer || typ.Elem().Kind() != reflect.Struct {
			t.Fatalf("formal model must be pointer to struct: %T", model)
		}
		value := reflect.ValueOf(model)
		tableName := value.MethodByName("TableName").Call(nil)[0].String()
		if seenTables[tableName] {
			t.Fatalf("duplicate model table %s", tableName)
		}
		seenTables[tableName] = true
		entityName := entityNameByTable(tableName)
		if entityName == "" {
			t.Fatalf("model table not in metadata: %s", tableName)
		}
		if fixture.PrimaryKeys[entityName] == "" {
			t.Fatalf("fixture missing primary key for %s", entityName)
		}
		structType := typ.Elem()
		foundPrimary := false
		for i := 0; i < structType.NumField(); i++ {
			field := structType.Field(i)
			tag := field.Tag.Get("gorm")
			if !hasGormFlag(tag, "primaryKey") {
				continue
			}
			foundPrimary = true
			if gormColumnName(tag) != fixture.PrimaryKeys[entityName] {
				t.Fatalf("%s primary field column %s, fixture %s", tableName, gormColumnName(tag), fixture.PrimaryKeys[entityName])
			}
		}
		if !foundPrimary {
			t.Fatalf("formal model %s missing primaryKey tag", tableName)
		}
		if structType.NumField() < 5 {
			t.Fatalf("formal model %s has too few fields", tableName)
		}
	}
	if len(seenTables) != 22 {
		t.Fatalf("unique formal model tables %d", len(seenTables))
	}
}

func entityNameByTable(table string) string {
	for _, entity := range DataModelV1Entities() {
		if entity.Table == table {
			return entity.Name
		}
	}
	return ""
}

func TestDataModelV1MigrationMatchesGoModelsAndFixture(t *testing.T) {
	fixture := loadDataModelFixture(t)
	ddl := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	if strings.Contains(ddl, "CREATE TABLE IF NOT EXISTS") {
		t.Fatalf("up must not use CREATE TABLE IF NOT EXISTS")
	}
	tableRe := regexp.MustCompile(`(?m)^CREATE TABLE ([a-z_]+) \(`)
	ddlTables := tableRe.FindAllStringSubmatch(ddl, -1)
	if len(ddlTables) != 22 {
		t.Fatalf("ddl table count %d", len(ddlTables))
	}
	ddlSet := map[string]bool{}
	for _, match := range ddlTables {
		ddlSet[match[1]] = true
	}
	for _, table := range fixture.Tables {
		if !ddlSet[table] {
			t.Fatalf("ddl missing table %s", table)
		}
	}
	models := DataModelV1FormalModels()
	modelSet := map[string]bool{}
	for _, model := range models {
		value := reflect.ValueOf(model)
		tableName := value.MethodByName("TableName").Call(nil)[0].String()
		modelSet[tableName] = true
		if !ddlSet[tableName] {
			t.Fatalf("ddl missing model table %s", tableName)
		}
	}
	if len(modelSet) != 22 {
		t.Fatalf("model table count %d", len(modelSet))
	}
	for table := range ddlSet {
		if !modelSet[table] {
			t.Fatalf("model missing table %s", table)
		}
	}
}

func TestDataModelV1DDLAndGoFieldsMatch(t *testing.T) {
	ddl := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	models := DataModelV1FormalModels()
	modelByTable := map[string]any{}
	for _, model := range models {
		value := reflect.ValueOf(model)
		tableName := value.MethodByName("TableName").Call(nil)[0].String()
		modelByTable[tableName] = model
	}
	for table, model := range modelByTable {
		ddlCols := parseDDLColumns(t, ddl, table)
		goCols := modelColumns(t, model)
		if len(ddlCols) != len(goCols) {
			t.Fatalf("%s column count ddl=%d go=%d", table, len(ddlCols), len(goCols))
		}
		for i := range ddlCols {
			if ddlCols[i].Name != goCols[i].Name {
				t.Fatalf("%s column order/name mismatch ddl=%s go=%s", table, ddlCols[i].Name, goCols[i].Name)
			}
			if ddlCols[i].Type != goCols[i].Type {
				t.Fatalf("%s.%s type mismatch ddl=%s go=%s", table, ddlCols[i].Name, ddlCols[i].Type, goCols[i].Type)
			}
			if ddlCols[i].Null != goCols[i].Null {
				t.Fatalf("%s.%s null mismatch ddlNull=%v goNull=%v", table, ddlCols[i].Name, ddlCols[i].Null, goCols[i].Null)
			}
		}
	}
}

func TestDataModelV1PrimaryKeyTypes(t *testing.T) {
	fixture := loadDataModelFixture(t)
	ddl := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	ulidSet := map[string]bool{}
	for _, entity := range fixture.ULIDEntities {
		ulidSet[entity] = true
	}
	for _, entity := range DataModelV1Entities() {
		cols := parseDDLColumns(t, ddl, entity.Table)
		found := false
		for _, col := range cols {
			if col.Name != entity.Primary {
				continue
			}
			found = true
			if ulidSet[entity.Name] {
				if col.Type != "CHAR(26) CHARACTER SET ASCII COLLATE ASCII_BIN" || col.Null {
					t.Fatalf("%s primary type mismatch: %s null=%v", entity.Table, col.Type, col.Null)
				}
			} else if entity.Name == "AuditLog" {
				if col.Type != "BIGINT UNSIGNED" || col.Null {
					t.Fatalf("audit_log primary mismatch: %s null=%v", col.Type, col.Null)
				}
				if !strings.Contains(segmentForTable(t, ddl, entity.Table), "AUTO_INCREMENT") {
					t.Fatalf("audit_log primary missing auto_increment")
				}
			}
		}
		if !found {
			t.Fatalf("missing primary column %s.%s", entity.Table, entity.Primary)
		}
	}
	for _, entity := range DataModelV1Entities() {
		segment := segmentForTable(t, ddl, entity.Table)
		if entity.Name == "AuditLog" {
			if !strings.Contains(segment, "AUTO_INCREMENT") {
				t.Fatalf("audit_log must contain AUTO_INCREMENT")
			}
			continue
		}
		if strings.Contains(segment, "AUTO_INCREMENT") {
			t.Fatalf("%s must not contain AUTO_INCREMENT", entity.Table)
		}
	}
}

func segmentForTable(t *testing.T, ddl, table string) string {
	t.Helper()
	pattern := regexp.MustCompile(`(?s)CREATE TABLE ` + regexp.QuoteMeta(table) + ` \((.*?)\n\) ENGINE=InnoDB`)
	match := pattern.FindStringSubmatch(ddl)
	if len(match) != 2 {
		t.Fatalf("segment not found %s", table)
	}
	return match[1]
}

func TestDataModelV1TaskIDForeignKeysAreAsciiCompatible(t *testing.T) {
	ddl := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	for _, table := range []string{"task_attempt", "task_stage", "task_event", "search_candidate", "task_article", "checkpoint"} {
		cols := parseDDLColumns(t, ddl, table)
		var taskType string
		for _, col := range cols {
			if col.Name == "task_id" {
				taskType = col.Type
				break
			}
		}
		if taskType != "CHAR(26) CHARACTER SET ASCII COLLATE ASCII_BIN" {
			t.Fatalf("%s.task_id type mismatch: %s", table, taskType)
		}
		segment := segmentForTable(t, ddl, table)
		if !strings.Contains(segment, "FOREIGN KEY (task_id) REFERENCES crawl_task (task_id)") {
			t.Fatalf("%s missing task FK", table)
		}
	}
}

func TestDataModelV1ReviewHoldWeakAndStrongReferences(t *testing.T) {
	ddl := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	segment := segmentForTable(t, ddl, "review_decision")
	for _, field := range []string{"hold_artifact_id", "hold_artifact_checksum", "evidence_schema_version", "evidence_snapshot"} {
		if !strings.Contains(segment, field) {
			t.Fatalf("review_decision missing %s", field)
		}
	}
	if !strings.Contains(segment, "FOREIGN KEY (hold_artifact_id) REFERENCES fetch_artifact (artifact_id) ON DELETE RESTRICT") {
		t.Fatalf("review_decision missing hold FK")
	}
	if strings.Contains(segment, "FOREIGN KEY (article_version_id) REFERENCES article_version") || strings.Contains(segment, "FOREIGN KEY (task_article_id) REFERENCES") {
		t.Fatalf("review_decision must not strongly reference periodic cleanup entities")
	}
}

func TestDataModelV1GlobalBlockFieldsAndConstraints(t *testing.T) {
	ddl := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	segment := segmentForTable(t, ddl, "global_block_entry")
	for _, field := range []string{"match_type", "pattern_normalized", "reason_code", "reason_summary", "evidence_ref", "effective_at", "expires_at", "created_by", "status", "version", "created_at", "updated_at"} {
		if !strings.Contains(segment, field) {
			t.Fatalf("global_block_entry missing %s", field)
		}
	}
	for _, legacyField := range []string{"block_type", "pattern VARCHAR", "reason VARCHAR", "basis"} {
		if strings.Contains(segment, legacyField) {
			t.Fatalf("global_block_entry must not keep alias %q", legacyField)
		}
	}
	if !strings.Contains(segment, "uq_global_block_active_pattern") || !strings.Contains(segment, "idx_global_block_status_effective") {
		t.Fatalf("global_block_entry missing lookup/active constraints")
	}
	if strings.Contains(strings.ToUpper(ddl), "AUDIT_SERVICE") {
		t.Fatalf("audit_service found")
	}
}

func TestDataModelV1TaskArticleIndexesAndFields(t *testing.T) {
	ddl := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	segment := segmentForTable(t, ddl, "task_article")
	for _, field := range []string{"persisted_at", "relevance_score", "review_state", "result_status", "task_article_id"} {
		if !strings.Contains(segment, field) {
			t.Fatalf("task_article missing %s", field)
		}
	}
	for _, index := range []string{"idx_task_article_task_persisted", "idx_task_article_task_relevance", "idx_task_article_task_review", "idx_task_article_task_status"} {
		if !strings.Contains(segment, index) {
			t.Fatalf("task_article missing %s", index)
		}
	}
	if strings.Contains(strings.ToUpper(segment), "CONTENT LONGTEXT") {
		t.Fatalf("task_article must not contain content")
	}
	if strings.Contains(segment, "matched_evidence, ") || strings.Contains(strings.ToLower(segment), "matched_evidence))") {
		t.Fatalf("task_article indexes must not include JSON")
	}
}

func TestDataModelV1DownIsFailClosed(t *testing.T) {
	down := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.down.sql")
	if !strings.Contains(down, "CREATE TEMPORARY TABLE dev004_b4_down_guard") || !strings.Contains(down, "DROP TEMPORARY TABLE dev004_b4_down_guard") {
		t.Fatalf("down missing fail-closed guard")
	}
	if strings.Contains(down, "dev004_b3_0002_down_guard") {
		t.Fatalf("down must not retain old persistent guard")
	}
	if strings.Contains(down, "CREATE PROCEDURE") || strings.Contains(down, "DROP PROCEDURE") || strings.Contains(down, "CALL ") || strings.Contains(down, "DELIMITER") {
		t.Fatalf("down must not use stored routines or DELIMITER")
	}
	if strings.Contains(down, "GROUP_CONCAT") || strings.Contains(down, "SIGNAL") {
		t.Fatalf("down must not rely on GROUP_CONCAT or SIGNAL")
	}
	if !strings.Contains(down, "COALESCE(SUM(") {
		t.Fatalf("down must use COUNT/COALESCE aggregation guards")
	}
	if strings.Contains(down, "DROP TABLE IF EXISTS") {
		t.Fatalf("down must not use DROP TABLE IF EXISTS")
	}
	if strings.Contains(down, "DROP TABLE articles") || strings.Contains(down, "DROP TABLE task_articles") {
		t.Fatalf("down must not drop 0001 tables")
	}
	dropRe := regexp.MustCompile(`(?m)^DROP TABLE ([a-z_]+);`)
	matches := dropRe.FindAllStringSubmatch(down, -1)
	if len(matches) != 22 {
		t.Fatalf("down table count %d", len(matches))
	}
}

func TestDataModelV1UpUsesSessionTemporaryGuard(t *testing.T) {
	up := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	for _, forbidden := range []string{"CREATE PROCEDURE", "DROP PROCEDURE", "CALL ", "DELIMITER", "GROUP_CONCAT", "SIGNAL"} {
		if strings.Contains(up, forbidden) {
			t.Fatalf("up must not contain %q", forbidden)
		}
	}
	for _, expected := range []string{
		"CREATE TEMPORARY TABLE dev004_b4_up_guard",
		"COALESCE(SUM(",
		"DEV004_B4_UP_FAIL_UNSUPPORTED_PREDECESSOR",
		"DEV004_B4_UP_FAIL_STRUCTURE_MISMATCH",
		"DEV004_B4_UP_FAIL_LEGACY_NOT_EMPTY",
		"DROP TEMPORARY TABLE dev004_b4_up_guard",
	} {
		if !strings.Contains(up, expected) {
			t.Fatalf("up missing %q", expected)
		}
	}
	structureIdx := strings.Index(up, "FROM information_schema.columns")
	legacyIdx := strings.Index(up, "FROM articles LIMIT 1")
	dropTempIdx := strings.Index(up, "DROP TEMPORARY TABLE dev004_b4_up_guard")
	createTableIdx := strings.Index(up, "CREATE TABLE admin ")
	if structureIdx < 0 || legacyIdx < 0 || dropTempIdx < 0 || createTableIdx < 0 {
		t.Fatalf("up guard ordering markers missing")
	}
	if structureIdx > legacyIdx {
		t.Fatalf("up reads legacy rows before structure guard")
	}
	if dropTempIdx > createTableIdx {
		t.Fatalf("up drops temporary guard after permanent DDL")
	}
	if strings.Contains(up, "CREATE EVENT") || strings.Contains(up, "CREATE TRIGGER") || strings.Contains(up, "CREATE TABLE IF NOT EXISTS dev004_b4_") {
		t.Fatalf("up must not create persistent guard objects")
	}
}

func TestMigrationExecutionContractDocument(t *testing.T) {
	path := filepath.Join("..", "..", "..", "migrations", "mysql", "README.md")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read migration README: %v", err)
	}
	content := string(data)
	for _, required := range []string{
		"fresh connection",
		"same connection",
		"stop on first error",
		"no --force",
		"close/discard",
		"non-transactional",
		"partial-state",
		"minimum_supported_mysql=8.0.16",
		"certified_mysql=8.0.46",
		"production_mysql=pinned_to_certified_version",
		"strict_all_tables",
	} {
		if !strings.Contains(strings.ToLower(content), required) {
			t.Fatalf("migration README missing %q", required)
		}
	}
	if strings.Contains(content, "MySQL 8.x") {
		t.Fatalf("migration README must not rely on broad MySQL 8.x wording")
	}
}

func TestMigrationSQLVersionAndStrictModePreflight(t *testing.T) {
	up := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.sql")
	down := readMigrationFile(t, "0002_v1_0_v1_1_22_entities.down.sql")
	for name, content := range map[string]string{"up": up, "down": down} {
		if !strings.Contains(content, "VERSION()") {
			t.Fatalf("%s missing VERSION() preflight", name)
		}
		if !strings.Contains(content, "DEV004_B6_"+strings.ToUpper(name)+"_FAIL_UNSUPPORTED_MYSQL_VERSION") {
			t.Fatalf("%s missing version guard identifier", name)
		}
		if !strings.Contains(content, "DEV004_B6_"+strings.ToUpper(name)+"_FAIL_STRICT_MODE_NOT_ACTIVE") {
			t.Fatalf("%s missing strict mode guard identifier", name)
		}
		if !strings.Contains(content, "SET SESSION sql_mode") {
			t.Fatalf("%s missing SET SESSION sql_mode", name)
		}
		if strings.Contains(content, "SET GLOBAL sql_mode") {
			t.Fatalf("%s must not modify GLOBAL sql_mode", name)
		}
		if !strings.Contains(content, "@@version_comment") || !strings.Contains(strings.ToLower(content), "%mariadb%") {
			t.Fatalf("%s must exclude MariaDB via VERSION and @@version_comment", name)
		}
		if !strings.Contains(content, "@dev004_b6_major = 8") || !strings.Contains(content, "@dev004_b6_minor = 0") || !strings.Contains(content, "@dev004_b6_patch >= 16") {
			t.Fatalf("%s missing exact 8.0 patch>=16 predicate", name)
		}
		versionIdx := strings.Index(content, "VERSION()")
		strictIdx := strings.Index(content, "SET SESSION sql_mode")
		guardName := "dev004_b4_up_guard"
		if name == "down" {
			guardName = "dev004_b4_down_guard"
		}
		guardIdx := strings.Index(content, "CREATE TEMPORARY TABLE "+guardName)
		if versionIdx < 0 || strictIdx < 0 || guardIdx < 0 || versionIdx > guardIdx || strictIdx > guardIdx {
			t.Fatalf("%s version/strict preflight must precede guard", name)
		}
		preflight := content[:guardIdx]
		if strings.Contains(preflight, "CHECK") {
			t.Fatalf("%s preflight must not use CHECK", name)
		}
		if !strings.Contains(preflight, "UNIQUE KEY DEV004_B6_"+strings.ToUpper(name)+"_FAIL_STRICT_MODE_NOT_ACTIVE") {
			t.Fatalf("%s strict guard missing named unique key", name)
		}
		if !strings.Contains(preflight, "UNIQUE KEY DEV004_B6_"+strings.ToUpper(name)+"_FAIL_UNSUPPORTED_MYSQL_VERSION") {
			t.Fatalf("%s version guard missing named unique key", name)
		}
		if !strings.Contains(preflight, "__dev004_b6_strict_base__") || !strings.Contains(preflight, "__dev004_b6_version_base__") {
			t.Fatalf("%s preflight must use duplicate base-key collision", name)
		}
	}
}

func TestEvidenceFileRenamedAndHistoryPreserved(t *testing.T) {
	oldPath := filepath.Join("..", "..", "..", "docs", "evidence", "dev004", "DEV004_B3_MYSQL8_VALIDATION.md")
	newPath := filepath.Join("..", "..", "..", "docs", "evidence", "dev004", "DEV004_MYSQL8_VALIDATION.md")
	if _, err := os.Stat(oldPath); !os.IsNotExist(err) {
		t.Fatalf("old evidence path must not exist")
	}
	data, err := os.ReadFile(newPath)
	if err != nil {
		t.Fatalf("read new evidence: %v", err)
	}
	content := string(data)
	for _, required := range []string{
		"ACCEPTED_HISTORICAL_SCOPE_DEVIATION_NON_PRECEDENTIAL",
		"UNAUTHORIZED_AT_EXECUTION",
		"crawler_dev004_guard_b4",
		"persisted_at <= ?",
		"task_article_id < ?",
		"ORDER BY persisted_at DESC, task_article_id DESC",
	} {
		if !strings.Contains(content, required) {
			t.Fatalf("evidence missing %q", required)
		}
	}
	if strings.Contains(content, "4 authorized") || strings.Contains(content, "four authorized") {
		t.Fatalf("evidence must not describe guard_b4 as authorized")
	}
}

func TestCanonicalULIDValidation(t *testing.T) {
	for _, valid := range []string{
		"00000000000000000000000000",
		"01ARZ3NDEKTSV4RRFFQ69G5FAV",
		"7ZZZZZZZZZZZZZZZZZZZZZZZZZ",
	} {
		if !IsCanonicalULIDV1(valid) {
			t.Fatalf("valid ULID rejected: %s", valid)
		}
	}
	for _, invalid := range []string{
		"01ARZ3NDEKTSV4RRFFQ69G5FA",       // too short
		"01ARZ3NDEKTSV4RRFFQ69G5FAV1",     // too long
		"01arz3ndektsv4rrffq69g5fav",      // lowercase
		"01ARZ3NDEKTSV4RRFFQ69G5FAL",      // contains L
		"01ARZ3NDEKTSV4RRFFQ69G5FAI",      // contains I
		"01ARZ3NDEKTSV4RRFFQ69G5FAO",      // contains O
		"01ARZ3NDEKTSV4RRFFQ69G5FAU",      // contains U
		"80000000000000000000000000",      // exceeds 128-bit ULID range
		"90000000000000000000000000",      // exceeds 128-bit ULID range
		"ZZZZZZZZZZZZZZZZZZZZZZZZZZ",      // exceeds 128-bit ULID range
		" 01ARZ3NDEKTSV4RRFFQ69G5FAV",     // leading whitespace
		"01ARZ3NDEKTSV4RRFFQ69G5FAV\n",    // trailing newline
		"01ARZ3NDEKTSV4RRFFQ69G5FA\u20ac", // non-ASCII and wrong length
	} {
		if IsCanonicalULIDV1(invalid) {
			t.Fatalf("invalid ULID accepted: %s", invalid)
		}
	}
}
