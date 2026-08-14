package store

import (
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"gorm.io/gorm/schema"
)

func parsedTableName(t *testing.T, model any) string {
	t.Helper()
	parsed, err := schema.Parse(model, &sync.Map{}, schema.NamingStrategy{})
	if err != nil {
		t.Fatalf("schema.Parse(%T): %v", model, err)
	}
	return parsed.Table
}

func TestLegacyModelsExplicitSingularTableNames(t *testing.T) {
	cases := []struct {
		model any
		want  string
	}{
		{Article{}, "article"},
		{Task{}, "task"},
		{CrawlLog{}, "crawl_log"},
	}
	for _, tc := range cases {
		if got := parsedTableName(t, tc.model); got != tc.want {
			t.Fatalf("%T table = %q, want %q", tc.model, got, tc.want)
		}
	}
}

func TestV2ModelsKeepV2TableNames(t *testing.T) {
	cases := []struct {
		model any
		want  string
	}{
		{ArticleV2{}, "articles"},
		{TaskArticleV2{}, "task_articles"},
	}
	for _, tc := range cases {
		if got := parsedTableName(t, tc.model); got != tc.want {
			t.Fatalf("%T table = %q, want %q", tc.model, got, tc.want)
		}
	}
}

func TestFiveTableNamesAreUnique(t *testing.T) {
	names := map[string]bool{}
	for _, model := range []any{Article{}, Task{}, CrawlLog{}, ArticleV2{}, TaskArticleV2{}} {
		name := parsedTableName(t, model)
		if names[name] {
			t.Fatalf("duplicate table name %q", name)
		}
		names[name] = true
	}
	if len(names) != 5 {
		t.Fatalf("expected 5 unique names, got %d", len(names))
	}
}

func TestArticleAndArticleV2UseDifferentTables(t *testing.T) {
	if parsedTableName(t, Article{}) == parsedTableName(t, ArticleV2{}) {
		t.Fatalf("Article and ArticleV2 must not share a table")
	}
}

func readRepoFile(t *testing.T, rel string) string {
	t.Helper()
	path := filepath.Join(repoRootForTest(), rel)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", rel, err)
	}
	return string(data)
}

func TestSchemaSQLDeclaresAllFiveTables(t *testing.T) {
	sql := readRepoFile(t, filepath.Join("config", "schema.sql"))
	for _, table := range []string{"article", "task", "crawl_log", "articles", "task_articles"} {
		if !strings.Contains(sql, "CREATE TABLE IF NOT EXISTS "+table) {
			t.Fatalf("config/schema.sql missing CREATE TABLE IF NOT EXISTS %s", table)
		}
	}
}

func TestMigrationKeepsV2TableNames(t *testing.T) {
	sql := readRepoFile(t, filepath.Join("migrations", "mysql", "0001_articles_task_articles_v2.sql"))
	if !strings.Contains(sql, "CREATE TABLE IF NOT EXISTS articles") ||
		!strings.Contains(sql, "CREATE TABLE IF NOT EXISTS task_articles") {
		t.Fatalf("migration must declare articles/task_articles")
	}
	if strings.Contains(sql, "CREATE TABLE IF NOT EXISTS article ") ||
		strings.Contains(sql, "CREATE TABLE IF NOT EXISTS task ") ||
		strings.Contains(sql, "CREATE TABLE IF NOT EXISTS crawl_log ") {
		t.Fatalf("migration must not declare legacy singular tables")
	}
}

func TestAutoMigrateStillLegacyOnly(t *testing.T) {
	source := readRepoFile(t, filepath.Join("go-spider", "internal", "store", "mysql.go"))
	if !strings.Contains(source, "AutoMigrate(&Article{}, &Task{}, &CrawlLog{})") {
		t.Fatalf("legacy AutoMigrate call changed")
	}
	if strings.Contains(source, "AutoMigrate(&ArticleV2") || strings.Contains(source, "AutoMigrate(&TaskArticleV2") {
		t.Fatalf("AutoMigrate must not include v2 models")
	}
	if strings.Contains(source, "NamingStrategy") || strings.Contains(source, "SingularTable") {
		t.Fatalf("mysql.go must not use global SingularTable/NamingStrategy override")
	}
}

func TestLegacyStoreMethodsStillUseLegacyModels(t *testing.T) {
	source := readRepoFile(t, filepath.Join("go-spider", "internal", "store", "mysql.go"))
	for _, fragment := range []string{
		"func (s *MySQLStore) SaveArticle(a *Article) error",
		"func (s *MySQLStore) SaveTask(t *Task) error",
		"func (s *MySQLStore) UpdateTask(id, status string, count int) error",
		"func (s *MySQLStore) QueryArticles(keyword string, limit int) ([]Article, error)",
		"s.db.Model(&Task{})",
	} {
		if !strings.Contains(source, fragment) {
			t.Fatalf("mysql.go missing legacy contract %q", fragment)
		}
	}
}
