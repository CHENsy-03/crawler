package store

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeArticleV2Tx struct {
	articles        map[string]*ArticleV2
	tasks           map[string]*TaskArticleV2
	nextArticleID   uint64
	nextTaskID      uint64
	createdArticles int
	createdTasks    int
	failArticle     bool
	failTask        bool
	failFindArticle bool
	failFindTask    bool
}

func newFakeArticleV2Tx() *fakeArticleV2Tx {
	return &fakeArticleV2Tx{
		articles: map[string]*ArticleV2{},
		tasks:    map[string]*TaskArticleV2{},
	}
}

func (f *fakeArticleV2Tx) FindArticleByKey(_ context.Context, key string) (*ArticleV2, bool, error) {
	if f.failFindArticle {
		return nil, false, errors.New("find article failed")
	}
	article, ok := f.articles[key]
	return article, ok, nil
}

func (f *fakeArticleV2Tx) CreateArticle(_ context.Context, article *ArticleV2) error {
	if f.failArticle {
		return errors.New("create article failed")
	}
	f.nextArticleID++
	article.ID = f.nextArticleID
	f.articles[article.ArticleKey] = article
	f.createdArticles++
	return nil
}

func (f *fakeArticleV2Tx) TouchArticleLastSeen(_ context.Context, id uint64, at time.Time) error {
	for _, article := range f.articles {
		if article.ID == id {
			article.LastSeenAt = at
			return nil
		}
	}
	return errors.New("article not found for touch")
}

func (f *fakeArticleV2Tx) FindTaskArticle(_ context.Context, taskID, hitID string) (*TaskArticleV2, bool, error) {
	if f.failFindTask {
		return nil, false, errors.New("find task article failed")
	}
	task, ok := f.tasks[taskID+"\x00"+hitID]
	return task, ok, nil
}

func (f *fakeArticleV2Tx) CreateTaskArticle(_ context.Context, task *TaskArticleV2) error {
	if f.failTask {
		return errors.New("create task article failed")
	}
	f.nextTaskID++
	task.ID = f.nextTaskID
	f.tasks[task.TaskID+"\x00"+task.HitID] = task
	f.createdTasks++
	return nil
}

func TestPersistFirstInsert(t *testing.T) {
	tx := newFakeArticleV2Tx()
	outcome, err := persistArticleResultV2Tx(context.Background(), tx, validArticleResultV2())
	if err != nil {
		t.Fatal(err)
	}
	if !outcome.Inserted || outcome.Replayed {
		t.Fatalf("unexpected outcome: %+v", outcome)
	}
	if outcome.ArticleID == nil || outcome.TaskArticleID == 0 {
		t.Fatalf("expected article and task ids")
	}
	if tx.createdArticles != 1 || tx.createdTasks != 1 {
		t.Fatalf("created articles=%d tasks=%d", tx.createdArticles, tx.createdTasks)
	}
}

func TestPersistReplayIsIdempotent(t *testing.T) {
	tx := newFakeArticleV2Tx()
	msg := validArticleResultV2()
	first, err := persistArticleResultV2Tx(context.Background(), tx, msg)
	if err != nil {
		t.Fatal(err)
	}
	msg.MessageID = "msg-replayed"
	msg.Timestamp = "2026-08-14T00:00:00Z"
	second, err := persistArticleResultV2Tx(context.Background(), tx, msg)
	if err != nil {
		t.Fatal(err)
	}
	if !second.Replayed || second.Inserted {
		t.Fatalf("expected replay: %+v", second)
	}
	if tx.createdArticles != 1 || tx.createdTasks != 1 {
		t.Fatalf("replay created duplicates: articles=%d tasks=%d", tx.createdArticles, tx.createdTasks)
	}
	if second.TaskArticleID != first.TaskArticleID {
		t.Fatalf("replay returned different task_articles id")
	}
}

func TestPersistConflictReturnsError(t *testing.T) {
	tx := newFakeArticleV2Tx()
	msg := validArticleResultV2()
	if _, err := persistArticleResultV2Tx(context.Background(), tx, msg); err != nil {
		t.Fatal(err)
	}
	conflict := validArticleResultV2()
	conflict.Content = "不同正文"
	conflict.ContentHash = sha256Hex(conflict.Content)
	_, err := persistArticleResultV2Tx(context.Background(), tx, conflict)
	if !errors.Is(err, ErrArticleResultConflict) {
		t.Fatalf("expected ErrArticleResultConflict, got %v", err)
	}
	if tx.createdTasks != 1 {
		t.Fatalf("conflict must not create another task_articles")
	}
}

func TestPersistConflictDoesNotOverwrite(t *testing.T) {
	tx := newFakeArticleV2Tx()
	msg := validArticleResultV2()
	if _, err := persistArticleResultV2Tx(context.Background(), tx, msg); err != nil {
		t.Fatal(err)
	}
	key := msg.TaskID + "\x00" + msg.HitID
	firstHash := tx.tasks[key].ResultHash
	conflict := validArticleResultV2()
	conflict.Status = "irrelevant"
	conflict.Score = 0
	if _, err := persistArticleResultV2Tx(context.Background(), tx, conflict); !errors.Is(err, ErrArticleResultConflict) {
		t.Fatalf("expected conflict error, got %v", err)
	}
	if tx.tasks[key].ResultHash != firstHash {
		t.Fatalf("existing task_articles must not be overwritten")
	}
}

func TestPersistArticleFailureNoTaskCreated(t *testing.T) {
	tx := newFakeArticleV2Tx()
	tx.failArticle = true
	if _, err := persistArticleResultV2Tx(context.Background(), tx, validArticleResultV2()); err == nil {
		t.Fatal("expected article create failure")
	}
	if tx.createdTasks != 0 {
		t.Fatalf("task must not be created after article failure")
	}
}

func TestPersistTaskFailureNoTaskCreated(t *testing.T) {
	tx := newFakeArticleV2Tx()
	tx.failTask = true
	if _, err := persistArticleResultV2Tx(context.Background(), tx, validArticleResultV2()); err == nil {
		t.Fatal("expected task create failure")
	}
	if tx.createdTasks != 0 {
		t.Fatalf("task must not be created on failure")
	}
}

func TestPersistExtractFailedArticleIDNil(t *testing.T) {
	tx := newFakeArticleV2Tx()
	msg := validArticleResultV2()
	msg.Content = ""
	msg.ContentHash = ""
	msg.Status = "extract_failed"
	outcome, err := persistArticleResultV2Tx(context.Background(), tx, msg)
	if err != nil {
		t.Fatal(err)
	}
	if !outcome.Inserted || outcome.ArticleID != nil {
		t.Fatalf("expected article_id NULL for extract_failed")
	}
	if tx.createdArticles != 0 || tx.createdTasks != 1 {
		t.Fatalf("unexpected creates: articles=%d tasks=%d", tx.createdArticles, tx.createdTasks)
	}
}

func TestPersistPreservesAllStatuses(t *testing.T) {
	for _, status := range []string{"accepted", "review_required", "irrelevant", "extract_failed", "unsupported_format"} {
		tx := newFakeArticleV2Tx()
		msg := validArticleResultV2()
		msg.Status = status
		if status == "extract_failed" || status == "unsupported_format" {
			msg.Content = ""
			msg.ContentHash = ""
		}
		if _, err := persistArticleResultV2Tx(context.Background(), tx, msg); err != nil {
			t.Fatalf("%s: %v", status, err)
		}
		key := msg.TaskID + "\x00" + msg.HitID
		if tx.tasks[key].Status != status {
			t.Fatalf("%s: stored status %q", status, tx.tasks[key].Status)
		}
	}
}
