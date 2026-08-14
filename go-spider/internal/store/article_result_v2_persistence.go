package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gorm.io/gorm"

	"crawler-platform/internal/protocol"
)

// PersistArticleResultV2Outcome reports what a persistence attempt did.
type PersistArticleResultV2Outcome struct {
	TaskArticleID uint64
	ArticleID     *uint64
	Inserted      bool
	Replayed      bool
}

// articleV2Tx is the transaction-scoped repository used by v2 persistence.
type articleV2Tx interface {
	FindArticleByKey(ctx context.Context, articleKey string) (*ArticleV2, bool, error)
	CreateArticle(ctx context.Context, article *ArticleV2) error
	TouchArticleLastSeen(ctx context.Context, id uint64, at time.Time) error
	FindTaskArticle(ctx context.Context, taskID, hitID string) (*TaskArticleV2, bool, error)
	CreateTaskArticle(ctx context.Context, article *TaskArticleV2) error
}

type gormArticleV2Tx struct {
	tx *gorm.DB
}

func (g *gormArticleV2Tx) FindArticleByKey(ctx context.Context, articleKey string) (*ArticleV2, bool, error) {
	var article ArticleV2
	err := g.tx.WithContext(ctx).Where("article_key = ?", articleKey).First(&article).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("find v2 article by key: %w", err)
	}
	return &article, true, nil
}

func (g *gormArticleV2Tx) CreateArticle(ctx context.Context, article *ArticleV2) error {
	if err := g.tx.WithContext(ctx).Create(article).Error; err != nil {
		return fmt.Errorf("create v2 article: %w", err)
	}
	return nil
}

func (g *gormArticleV2Tx) TouchArticleLastSeen(ctx context.Context, id uint64, at time.Time) error {
	if err := g.tx.WithContext(ctx).Model(&ArticleV2{}).Where("id = ?", id).Update("last_seen_at", at).Error; err != nil {
		return fmt.Errorf("touch v2 article last_seen_at: %w", err)
	}
	return nil
}

func (g *gormArticleV2Tx) FindTaskArticle(ctx context.Context, taskID, hitID string) (*TaskArticleV2, bool, error) {
	var taskArticle TaskArticleV2
	err := g.tx.WithContext(ctx).Where("task_id = ? AND hit_id = ?", taskID, hitID).First(&taskArticle).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("find v2 task article: %w", err)
	}
	return &taskArticle, true, nil
}

func (g *gormArticleV2Tx) CreateTaskArticle(ctx context.Context, taskArticle *TaskArticleV2) error {
	if err := g.tx.WithContext(ctx).Create(taskArticle).Error; err != nil {
		return fmt.Errorf("create v2 task article: %w", err)
	}
	return nil
}

// PersistArticleResultV2 validates and stores an ArticleResultV2 inside a single
// MySQL transaction. It is a contract entry point and is NOT yet wired to any
// production consumer.
func (s *MySQLStore) PersistArticleResultV2(ctx context.Context, msg *protocol.ArticleResultV2) (PersistArticleResultV2Outcome, error) {
	if s == nil || s.db == nil {
		return PersistArticleResultV2Outcome{}, fmt.Errorf("mysql store is not initialized")
	}
	var outcome PersistArticleResultV2Outcome
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		next, err := persistArticleResultV2Tx(ctx, &gormArticleV2Tx{tx: tx}, msg)
		outcome = next
		return err
	})
	return outcome, err
}

func persistArticleResultV2Tx(ctx context.Context, tx articleV2Tx, msg *protocol.ArticleResultV2) (PersistArticleResultV2Outcome, error) {
	records, err := BuildArticleResultV2Records(msg)
	if err != nil {
		return PersistArticleResultV2Outcome{}, err
	}

	existingTask, found, err := tx.FindTaskArticle(ctx, msg.TaskID, msg.HitID)
	if err != nil {
		return PersistArticleResultV2Outcome{}, err
	}
	if found {
		if existingTask.ResultHash == records.ResultHash {
			return PersistArticleResultV2Outcome{
				TaskArticleID: existingTask.ID,
				ArticleID:     existingTask.ArticleID,
				Replayed:      true,
			}, nil
		}
		return PersistArticleResultV2Outcome{}, fmt.Errorf(
			"%w: task_id=%s hit_id=%s", ErrArticleResultConflict, msg.TaskID, msg.HitID,
		)
	}

	var articleID *uint64
	if records.Article != nil {
		now := time.Now().UTC()
		existingArticle, foundArticle, err := tx.FindArticleByKey(ctx, records.Article.ArticleKey)
		if err != nil {
			return PersistArticleResultV2Outcome{}, err
		}
		if foundArticle {
			if err := tx.TouchArticleLastSeen(ctx, existingArticle.ID, now); err != nil {
				return PersistArticleResultV2Outcome{}, err
			}
			articleID = &existingArticle.ID
		} else {
			records.Article.FirstSeenAt = now
			records.Article.LastSeenAt = now
			if err := tx.CreateArticle(ctx, records.Article); err != nil {
				return PersistArticleResultV2Outcome{}, err
			}
			articleID = &records.Article.ID
		}
		records.TaskArticle.ArticleID = articleID
	}

	records.TaskArticle.CreatedAt = time.Now().UTC()
	if err := tx.CreateTaskArticle(ctx, &records.TaskArticle); err != nil {
		return PersistArticleResultV2Outcome{}, err
	}

	return PersistArticleResultV2Outcome{
		TaskArticleID: records.TaskArticle.ID,
		ArticleID:     articleID,
		Inserted:      true,
	}, nil
}
