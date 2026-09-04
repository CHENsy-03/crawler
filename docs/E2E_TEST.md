# 通用爬虫系统端到端集成测试

## 1. 测试目标

验证整条采集流水线的端到端正确性：

`
API 创建任务 → crawler:search → Python Search Worker → crawler:url
→ Go 下载 Worker → crawler:html → Python Parser Worker → crawler:result
→ Go Result Consumer → MySQL → API 查询
`

## 2. 环境要求

- Docker Desktop
- Python 3.14+ with pytest, redis
- Go 1.26+ with gorm

## 3. 启动环境

本节所有命令均从当前 Git 仓库根目录执行；仓库根目录定义为包含当前 `.git`、`README.md`、`tests/` 的目录。

可先使用 `git rev-parse --show-toplevel` 核验当前位置；如不在仓库根目录，应切换到该命令输出的目录。

```bash
cd "$(git rev-parse --show-toplevel)"
docker-compose up -d redis mysql
# 等待 MySQL 就绪后:
python -m pytest tests/integration/
```

## 4. 测试场景

### 4.1 全部成功

- 流程：搜索 3 篇 → 下载 → 解析 → 入库 → completed
- 断言：Stored == Expected

### 4.2 部分失败

- 流程：搜索 3 篇 → 1 篇下载 403 → 2 篇入库 → completed_with_errors
- 断言：Stored > 0, Failed > 0

### 4.3 全部失败

- 流程：搜索 3 篇 → 全部下载 403 → 0 篇入库 → failed
- 断言：Stored == 0, Failed > 0

### 4.4 空搜索

- 流程：搜索返回 0 篇 → completed
- 断言：Expected == 0

## 5. 额外验证

- [ ] Redis 各队列最终清空
- [ ] MySQL Article 字段完整且 URL 幂等
- [ ] 重复错误不重复增 Failed
- [ ] 服务重启不重复文章
- [ ] Parser 唯一消费者
- [ ] 所有 Consumer 优雅停止
- [ ] API 不在入库前返回 completed

## 6. 验收

`
python -m pytest -q
go test ./go-spider/...
go vet ./go-spider/...
git status --short
git log --oneline --decorate -10
`

## 7. TASK-019B-8：本地全链 v2 E2E

- 使用 `scripts/task019b8-e2e.ps1` 与 `tests/integration/task019b8/compose.yml`。
- 从 URLMessageV2 开始，本地 httptest，隔离 Redis/MySQL。
- 覆盖多 hit 一次下载、长正文、canonical、标题/日期、accepted/review_required/irrelevant/extract_failed、PDF MIME 拒绝、非法版本隔离、重复投递。
- 正式路径为 `crawler:url → Go 下载 → crawler:html → Python parser → crawler:result → Go 持久化`。
- 未覆盖 `crawler:search/SearchPlan`。
