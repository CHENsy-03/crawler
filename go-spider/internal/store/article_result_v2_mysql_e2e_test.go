package store

import (
	"os"
	"strings"
	"testing"
)

func requireB7E2E(t *testing.T) {
	t.Helper()
	if os.Getenv("TASK019B7_E2E") != "1" {
		t.Skip("TASK019B7_E2E integration test is disabled")
	}
	if os.Getenv("TASK019B7_MYSQL_DSN") == "" {
		t.Fatal("TASK019B7_MYSQL_DSN is required for B7 E2E")
	}
}

func openB7Store(t *testing.T) *MySQLStore {
	t.Helper()
	requireB7E2E(t)
	store, err := NewMySQLStore(os.Getenv("TASK019B7_MYSQL_DSN"))
	if err != nil {
		t.Fatalf("NewMySQLStore: %v", err)
	}
	sqlDB, err := store.db.DB()
	if err != nil {
		t.Fatalf("underlying sql.DB: %v", err)
	}
	t.Cleanup(func() { _ = sqlDB.Close() })
	return store
}

func b7TableSet(t *testing.T, s *MySQLStore) map[string]bool {
	t.Helper()
	rows, err := s.db.Raw("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()").Rows()
	if err != nil {
		t.Fatalf("query tables: %v", err)
	}
	defer rows.Close()
	set := map[string]bool{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatalf("scan table: %v", err)
		}
		set[name] = true
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate tables: %v", err)
	}
	return set
}

func b7ColumnType(t *testing.T, s *MySQLStore, table, column string) string {
	t.Helper()
	var dataType string
	err := s.db.Raw(`SELECT DATA_TYPE FROM information_schema.COLUMNS
		WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?`, table, column).Scan(&dataType).Error
	if err != nil {
		t.Fatalf("column type %s.%s: %v", table, column, err)
	}
	return dataType
}

func b7ColumnNullable(t *testing.T, s *MySQLStore, table, column string) string {
	t.Helper()
	var nullable string
	err := s.db.Raw(`SELECT IS_NULLABLE FROM information_schema.COLUMNS
		WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?`, table, column).Scan(&nullable).Error
	if err != nil {
		t.Fatalf("column nullable %s.%s: %v", table, column, err)
	}
	return nullable
}

func b7ColumnKey(t *testing.T, s *MySQLStore, table, column string) string {
	t.Helper()
	var key string
	err := s.db.Raw(`SELECT COLUMN_KEY FROM information_schema.COLUMNS
		WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?`, table, column).Scan(&key).Error
	if err != nil {
		t.Fatalf("column key %s.%s: %v", table, column, err)
	}
	return key
}

func b7HasIndexColumn(t *testing.T, s *MySQLStore, table, index, column string) bool {
	t.Helper()
	var count int64
	err := s.db.Raw(`SELECT COUNT(*) FROM information_schema.STATISTICS
		WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND INDEX_NAME = ? AND COLUMN_NAME = ?`,
		table, index, column).Scan(&count).Error
	if err != nil {
		t.Fatalf("index %s.%s: %v", table, index, err)
	}
	return count > 0
}

func b7HasConstraint(t *testing.T, s *MySQLStore, table, name, ctype string) bool {
	t.Helper()
	var count int64
	err := s.db.Raw(`SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
		WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = ? AND CONSTRAINT_NAME = ? AND CONSTRAINT_TYPE = ?`,
		table, name, ctype).Scan(&count).Error
	if err != nil {
		t.Fatalf("constraint %s.%s: %v", table, name, err)
	}
	return count > 0
}

func b7HasForeignKeyTo(t *testing.T, s *MySQLStore, table, referenced string) bool {
	t.Helper()
	var count int64
	err := s.db.Raw(`SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
		WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = ? AND REFERENCED_TABLE_NAME = ?`,
		table, referenced).Scan(&count).Error
	if err != nil {
		t.Fatalf("foreign key %s -> %s: %v", table, referenced, err)
	}
	return count > 0
}

func TestTask019B7LegacyBootstrap(t *testing.T) {
	s := openB7Store(t)
	tables := b7TableSet(t, s)
	for _, name := range []string{"article", "task", "crawl_log"} {
		if !tables[name] {
			t.Fatalf("legacy table %s missing", name)
		}
	}
	for _, name := range []string{"articles", "task_articles", "tasks", "crawl_logs"} {
		if tables[name] {
			t.Fatalf("v2/plural table %s must not exist before migration", name)
		}
	}
}

func TestTask019B7SchemaAfterMigration(t *testing.T) {
	s := openB7Store(t)
	tables := b7TableSet(t, s)
	for _, name := range []string{"article", "task", "crawl_log", "articles", "task_articles"} {
		if !tables[name] {
			t.Fatalf("table %s missing after migration", name)
		}
	}

	if got := b7ColumnType(t, s, "articles", "content"); got != "longtext" {
		t.Fatalf("articles.content type = %q", got)
	}
	if got := b7ColumnKey(t, s, "articles", "article_key"); got != "UNI" {
		t.Fatalf("articles.article_key key = %q", got)
	}
	for _, idx := range []string{"idx_articles_identity_url_hash", "idx_articles_content_hash", "idx_articles_publish_date"} {
		if !b7HasIndexColumn(t, s, "articles", idx, strings.TrimPrefix(idx, "idx_articles_")) {
			t.Fatalf("missing articles index %s", idx)
		}
	}

	if got := b7ColumnNullable(t, s, "task_articles", "article_id"); got != "YES" {
		t.Fatalf("task_articles.article_id nullable = %q", got)
	}
	if got := b7ColumnType(t, s, "task_articles", "matched_evidence"); got != "json" {
		t.Fatalf("task_articles.matched_evidence type = %q", got)
	}
	if !b7HasConstraint(t, s, "task_articles", "uq_task_articles_task_hit", "UNIQUE") {
		t.Fatalf("missing UNIQUE(task_id, hit_id)")
	}
	if !b7HasForeignKeyTo(t, s, "task_articles", "articles") {
		t.Fatalf("missing task_articles FK to articles")
	}

	// articles must not contain legacy Article-only fields.
	for _, column := range []string{"url", "province", "site", "keyword", "score", "matched_keywords", "crawl_time", "detail_fetched", "source_type"} {
		var count int64
		err := s.db.Raw(`SELECT COUNT(*) FROM information_schema.COLUMNS
			WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'articles' AND COLUMN_NAME = ?`, column).Scan(&count).Error
		if err != nil {
			t.Fatal(err)
		}
		if count != 0 {
			t.Fatalf("articles must not contain legacy column %s", column)
		}
	}

	// Re-running NewMySQLStore after migration must not add v2 tables through AutoMigrate.
	_ = openB7Store(t)
	after := b7TableSet(t, s)
	for _, name := range []string{"articles", "task_articles"} {
		if !after[name] {
			t.Fatalf("v2 table %s disappeared after NewMySQLStore", name)
		}
	}
}
