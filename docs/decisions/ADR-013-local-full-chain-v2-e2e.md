# ADR-013：本地全链 v2 E2E（TASK-019B-8）

**状态：** completed

**日期：** 2026-08-14

**关联：** TASK-019B-8，TASK-019B-8R，ADR-012

## 验证环境

- Docker Client/Server 29.6.2，Docker Desktop 4.83.0，Compose v5.3.1，Linux containers
- MySQL `mysql:8.0`，Redis `redis:7-alpine`
- Python 3.14.7，Go 1.26.5，GCC 16.2.0/MSYS2 UCRT64
- 唯一 Compose project，loopback 随机端口，随机十六进制密码

## 验证范围

- 从 `URLMessageV2` 开始，不包含 `crawler:search/SearchPlan`。
- 使用本地 `httptest`，不访问外部网站。
- 使用正式 Go Pool、Python parser 子进程和正式 `crawler:url/html/result` 队列。
- 真实路径：`crawler:url → PopURLDispatch → V2DownloadCoordinator/FetchHTML → PushHTMLMessageV2 → Python parser → ArticleResultV2 → PopResultDispatch → PersistArticleResultV2 → MySQL`。

## 结果

- 两个 hit 共用一次逻辑下载，`/redirect` 与 `/article` 各请求一次。
- 长正文完整写入 `articles.content`，无截断，噪声被清理，content_hash 一致。
- h1 优先于 HTML title；详情日期优先于 `published_at`；canonical 相对地址正确且未被请求。
- accepted、expanded-only review_required、snippet-only review_required、irrelevant、extract_failed 均真实贯通并持久化。
- 非 HTML PDF MIME 被下载边界拒绝，不生成 HTMLMessageV2/ArticleResultV2/unsupported_format。
- 非法 URLMessageV2（含 `protocol_version=null`）不触发 HTTP，不写库，不产生 v1 错误；后续合法消息贯通。
- 上游重复投递不增加 task_articles/articles，不触发额外 HTTP。
- legacy/v2 五表并存；migration 独立显式执行，未自动接入生产启动。
- 测试结束容器、网络、卷残留均为 0。

## 残余风险

- Redis List BRPOP 无 ACK、重试、死信和背压。
- B8 未覆盖 `crawler:search/SearchPlan`。
- migration 未获准用于现有数据库。