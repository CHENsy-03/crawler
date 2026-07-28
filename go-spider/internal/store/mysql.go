package store

import (
	"fmt"
	"log"
	"os"
	"time"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

type Article struct {
	ID              uint      `gorm:"primaryKey" json:"id"`
	URL             string    `gorm:"type:varchar(1000);not null;uniqueIndex:idx_url_hash,length:32" json:"url"`
	Title           string    `gorm:"type:varchar(500)" json:"title"`
	Summary         string    `gorm:"type:text" json:"summary"`
	Content         string    `gorm:"type:longtext" json:"content"`
	PublishTime     time.Time `json:"publish_time"`
	Province        string    `gorm:"type:varchar(100)" json:"province"`
	Site            string    `gorm:"type:varchar(200)" json:"site"`
	Keyword         string    `gorm:"type:varchar(200)" json:"keyword"`
	Score           int       `gorm:"default:0" json:"score"`
	MatchedKeywords string    `gorm:"type:varchar(500)" json:"matched_keywords"`
	CrawlTime       time.Time `json:"crawl_time"`
	DetailFetched   bool      `gorm:"default:false" json:"detail_fetched"`
	SourceType      string    `gorm:"type:varchar(50)" json:"source_type"`
	Status          string    `gorm:"type:varchar(20);default:new" json:"status"`
	CreatedAt       time.Time `json:"created_at"`
}

type Task struct {
	ID           string    `gorm:"type:varchar(32);primaryKey" json:"id"`
	Keyword      string    `gorm:"type:varchar(200)" json:"keyword"`
	Site         string    `gorm:"type:varchar(100)" json:"site"`
	Status       string    `gorm:"type:varchar(32);default:created" json:"status"`
	ArticleCount int       `gorm:"default:0" json:"article_count"`
	CreatedAt    time.Time `json:"created_at"`
}

type CrawlLog struct {
	ID        uint      `gorm:"primaryKey" json:"id"`
	URL       string    `gorm:"type:varchar(1000);not null" json:"url"`
	Status    int       `gorm:"not null" json:"status"`
	CostMs    int       `gorm:"default:0" json:"cost_ms"`
	Error     string    `gorm:"type:text" json:"error"`
	CreatedAt time.Time `json:"created_at"`
}

type MySQLStore struct {
	db *gorm.DB
}

func NewMySQLStore(dsn string) (*MySQLStore, error) {
	if dsn == "" {
		dsn = fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=True",
			envDefault("MYSQL_USER", "root"),
			envDefault("MYSQL_PASSWORD", ""),
			envDefault("MYSQL_HOST", "localhost"),
			envDefault("MYSQL_PORT", "3306"),
			envDefault("MYSQL_DATABASE", "crawler_db"),
		)
	}

	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Warn),
	})
	if err != nil {
		return nil, fmt.Errorf("mysql connect: %w", err)
	}

	if err := db.AutoMigrate(&Article{}, &Task{}, &CrawlLog{}); err != nil {
		return nil, fmt.Errorf("auto migrate: %w", err)
	}

	log.Println("[store] MySQL connected, tables migrated")
	return &MySQLStore{db: db}, nil
}

func (s *MySQLStore) SaveArticle(a *Article) error {
	return s.db.Where("url = ?", a.URL).Assign(a).FirstOrCreate(a).Error
}

func (s *MySQLStore) SaveTask(t *Task) error {
	return s.db.Where("id = ?", t.ID).Assign(t).FirstOrCreate(t).Error
}

func (s *MySQLStore) UpdateTask(id, status string, count int) error {
	result := s.db.Model(&Task{}).Where("id = ?", id).Updates(map[string]interface{}{
		"status": status, "article_count": count,
	})
	if result.Error != nil {
		log.Printf("[store] UpdateTask error: id=%s status=%s count=%d err=%v", id, status, count, result.Error)
		return fmt.Errorf("update task %s status=%s: %w", id, status, result.Error)
	}
	if result.RowsAffected == 0 {
		log.Printf("[store] UpdateTask: no rows affected: id=%s status=%s count=%d", id, status, count)
	}
	return nil
}

func (s *MySQLStore) LogCrawl(url string, httpStatus, costMs int, errMsg string) {
	s.db.Create(&CrawlLog{
		URL: url, Status: httpStatus, CostMs: costMs, Error: errMsg,
	})
}

func (s *MySQLStore) QueryArticles(keyword string, limit int) ([]Article, error) {
	var articles []Article
	q := s.db.Order("score DESC").Limit(limit)
	if keyword != "" {
		q = q.Where("title LIKE ?", "%"+keyword+"%")
	}
	err := q.Find(&articles).Error
	return articles, err
}

func envDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
