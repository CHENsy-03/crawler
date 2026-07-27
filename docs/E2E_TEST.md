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

`ash
cd workspace/crawler
docker-compose up -d redis mysql
# 等待 MySQL 就绪后:
python -m pytest tests/integration/
`

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