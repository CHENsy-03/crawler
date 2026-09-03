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

一次性 migration job 不属于长期运行服务，不计入九服务拓扑。

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
- go-api：`/healthz` liveness、`/readyz` readiness，作为内部容器探针，不进入外部业务 OpenAPI。
- python-worker：进程存活 liveness，依赖就绪后启动。
- web/nginx：HTTP 探针。
- prometheus/grafana：自身探针。
- go-api 在 MySQL/Redis readiness 前不得标记 ready。
- Python Worker 在 Redis Streams/MySQL 可用后启动。

### 6.1 启动顺序

1. MySQL、Redis
2. 一次性 migration job
3. Go API 与 Outbox dispatcher
4. Python workers
5. Web
6. Nginx
7. Prometheus/Grafana 按依赖启动

migration job 完成后退出，不保持长期运行。

## 7. 资源限制与背压

| 服务 | CPU reservation | CPU hard limit | Memory reservation | Memory hard limit |
|---|---:|---:|---:|---:|
| nginx | 0.25 | 1.0 | 128MiB | 512MiB |
| web | 0.25 | 1.0 | 256MiB | 1GiB |
| go-api | 0.5 | 2.0 | 512MiB | 2GiB |
| python-worker | 0.5 | 2.0 | 1GiB | 3GiB |
| python-playwright-worker | 0.5 | 2.0 | 1GiB | 4GiB |
| redis | 0.25 | 1.0 | 256MiB | 1GiB |
| mysql | 1.0 | 4.0 | 1GiB | 4GiB |
| prometheus | 0.25 | 1.0 | 512MiB | 2GiB |
| grafana | 0.25 | 1.0 | 256MiB | 1GiB |

资源预算适用于单机内网部署，总量不能超过目标主机可用资源。Playwright Worker 必须有独立内存限制。超限触发背压和拒绝策略，不允许宿主机失控。

- worker 按队列 lag 和资源压力拒绝或暂停新任务。
- 最多 3 个活动任务；单任务默认 20 关键词、100 页、10000 候选、2 小时。
- 磁盘、内存、CPU 和队列压力触发背压和拒绝策略。

### 7.1 两层 HTTP 限制

A. SEALED transport 硬上限：

- DNS timeout=5 秒、connect timeout=5 秒、TLS timeout=5 秒
- response header timeout=10 秒、read idle timeout=15 秒
- probe total=30 秒、search total=30 秒、detail total=60 秒
- request body=1MiB、response headers=256KiB
- probe response body=1MiB、search response body=8MiB、detail response body=20MiB
- redirects 最多 3 跳
- transport global_active=20、per_host_active=5、per_host_idle=2

B. TARGET_V1 产品调度默认值：

- global active tasks HTTP budget=16
- 单域默认=2
- 产品允许配置的单域上限=4

产品调度值必须小于等于 transport 硬上限，且产品调度层尚未完整接入，不得写成已实现。V1 附件经安全 transport 时当前有效硬上限为 detail profile 的 20MiB，不宣称 50MB。

Python Worker 不直接执行 MySQL 业务权威写入；结果经版本化事件交付，由 Go Result Consumer 执行权威写入。

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
