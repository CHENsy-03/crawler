package store

import (
	"strings"
	"testing"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

func connectTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	dsn := "root:@tcp(localhost:3306)/crawler_db?charset=utf8mb4&parseTime=True"
	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		t.Skipf("MySQL not available: %v", err)
	}
	return db
}

func brokenStore(t *testing.T) *MySQLStore {
	t.Helper()
	db := connectTestDB(t)
	// Close the underlying connection pool to simulate DB failure
	sqlDB, err := db.DB()
	if err != nil {
		t.Skipf("failed to get underlying sql.DB: %v", err)
	}
	if err := sqlDB.Close(); err != nil {
		t.Skipf("failed to close sql.DB: %v", err)
	}
	return &MySQLStore{db: db}
}

func TestUpdateTaskSuccess(t *testing.T) {
	db := connectTestDB(t)
	s := &MySQLStore{db: db}

	taskID := "ut-" + t.Name()
	s.db.Create(&Task{ID: taskID, Keyword: "test", Site: "test", Status: "created"})
	t.Cleanup(func() {
		s.db.Unscoped().Delete(&Task{}, "id = ?", taskID)
	})

	err := s.UpdateTask(taskID, "completed", 5)
	if err != nil {
		t.Fatalf("UpdateTask returned error: %v", err)
	}

	var task Task
	if err := s.db.First(&task, "id = ?", taskID).Error; err != nil {
		t.Fatalf("failed to read task: %v", err)
	}
	if task.Status != "completed" {
		t.Fatalf("status = %q, want %q", task.Status, "completed")
	}
	if task.ArticleCount != 5 {
		t.Fatalf("article_count = %d, want %d", task.ArticleCount, 5)
	}
}

func TestUpdateTaskErrorOnInvalidDB(t *testing.T) {
	s := brokenStore(t)
	err := s.UpdateTask("nonexistent-id", "completed", 1)
	if err == nil {
		t.Fatal("UpdateTask: expected error for closed DB connection, got nil")
	}
	if !strings.Contains(err.Error(), "update task") {
		t.Fatalf("error message should contain 'update task', got: %v", err)
	}
}

func TestUpdateTaskNonExistentRow(t *testing.T) {
	db := connectTestDB(t)
	s := &MySQLStore{db: db}

	err := s.UpdateTask("non-existent-"+t.Name(), "completed", 1)
	if err != nil {
		t.Fatalf("UpdateTask on non-existent row returned error: %v", err)
	}
}
