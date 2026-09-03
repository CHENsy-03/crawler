# 通用型爬虫目标部署架构

本文描述 V1 单机内网 Docker Compose 目标拓扑。当前 `docker-compose.yml` 不是该目标拓扑，本文不修改任何 Compose 文件。

## 1. 目标服务拓扑

| 服务 | 角色 | 外部端口 | 内部端口 |
|---|---|---|---|
| nginx | 同源入口、TLS 终止、静态资源/Web 反代 | 443/80 | 80/8443 内部可选 |
| web | React SPA 静态服务 | 无 | 3000/8080 内部 |
| go-api | 唯一外部业务网关 | 无 | 8080 内部 |
| python-worker | 发现/业务抓取/解析/评分/去重/附件 Worker | 无 | 无 |
| python-playwright-worker | 隔离 JS 渲染降级 Worker | 无 | 无 |
| redis | Redis Streams 消息和缓存 | 无 | 6379 内部 |
| mysql | 业务权威数据库 | 无 | 3306 内部 |
| prometheus | 指标采集 | 内部可选 | 9090 内部 |
| grafana | 指标展示 | 内部可选 | 3001 内部 |

## 2. 网络区

- `edge`：nginx 唯一对外暴露层。
- `app`：web、go-api、python worker、redis、mysql 的内部网络。
- `observability`：prometheus/grafana 与 app 指标抓取。
- worker 不得从公网直接暴露。
- go-api 只能被 nginx 和本地受控运维访问。

## 3. 端口暴露原则

- 对外只暴露 443（HTTPS）和受控的 80 重定向。
- MySQL、Redis、Prometheus、Grafana 默认不绑定公网。
- 内部监控端口如确需访问，只允许内网或 SSH 隧道。
- 开发环境允许本机端口映射，但 production 边界以 nginx 为唯一入口。

## 4. 卷设计

| 卷 | 用途 |
|---|---|
| mysql_data | MySQL 数据 |
| raw_evidence | 不可变原始页面/附件 |
| export_files | 导出文件 |
| duckdb_analysis | DuckDB 分析文件 |
| prometheus_data | 指标历史 |
| grafana_data | 看板配置 |
| logs | 容器日志或等价日志输出 |

原始证据卷和导出文件卷不得放在 Web 静态目录。

## 5. Secrets

- 生产密钥通过 Docker secrets 或等价机制提供。
- 至少覆盖：MySQL 密码、Redis 密码、Session secret、bootstrap secret、备份加密密钥。
- 密钥不进入镜像、Compose 明文值、环境输出或日志。
- 配置优先级：sealed security > server > site > task。

## 6. Healthcheck 与启动顺序

- mysql：`mysqladmin ping` readiness。
- redis：`redis-cli ping` readiness。
- go-api：`/system/health` liveness、`/system/readiness` readiness。
- python-worker：进程存活 liveness，依赖就绪后启动。
- web/nginx：HTTP 探针。
- prometheus/grafana：自身探针。
- go-api 在 MySQL/Redis readiness 前不得标记 ready。
- Python Worker 在 Redis Streams/MySQL 可用后启动。

## 7. 资源限制与背压

- 每个服务设置 CPU/memory 上限。
- worker 按队列 lag 和资源压力拒绝或暂停新任务。
- 全局 HTTP 并发默认 16；单域默认 2、上限 4。
- 最多 3 个活动任务；单任务默认 20 关键词、100 页、10000 候选、2 小时。
- 磁盘、内存、CPU 和队列压力触发背压和拒绝策略。

## 8. 备份与恢复

- 每日加密备份 MySQL、原始证据、导出文件和关键配置。
- 保留 7 个日备份和 4 个周备份。
- RPO ≤ 24 小时，RTO ≤ 4 小时。
- 备份脱离 Docker volume 所在主盘或使用加密对象/异地目录。
- 每季度或发布前执行恢复演练并记录结果。

## 9. TLS

- nginx 终止 TLS，证书由内网 CA 或受控证书管理提供。
- 浏览器和管理面板只通过 HTTPS 同源访问。
- 内部服务间使用网络隔离，MySQL/Redis 不暴露明文公网。

## 10. 当前 Compose 差距

当前 `docker-compose.yml`：

- 不含完整 go-api/web/python-worker/nginx 产品拓扑。
- MySQL 等运行配置与目标 secrets 策略不一致。
- 无原始证据卷、export 卷和完整 observability 接入。
- 不代表生产部署配置。

目标 Compose 文件将在部署实施任务中建立，本 BUILD 不创建或修改运行配置。

## 11. 验收条件

- 单机冷启动后所有服务 readiness 通过。
- 仅 443/80 对外可达。
- 备份恢复演练达到 RPO/RTO 目标。
- 无明文 secrets、无公网 MySQL/Redis/管理端口。
