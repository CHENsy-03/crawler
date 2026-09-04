# ADR-024: Go 作为唯一外部业务网关

**状态：** Accepted
**日期：** 2026-09-03
**关联：** PD-031、PD-032、PD-033；ADR-001；TASK-020A

## Context

当前 repository 同时存在 Go API、Go CLI、Python FastAPI `api/server.py`、Python CLI 和历史 Go Worker 下载主链。冻结决策要求 Go 是唯一外部业务网关，Python 是采集核心，但当前实现与目标职责并不一致。

## Decision

目标职责冻结如下：

- Go 负责外部 API、认证、Session、API Token、任务状态、SSE、调度协调和 MySQL 权威写入协调。
- Python 负责发现、业务抓取、解析、评分、过滤、去重和附件处理。
- Python FastAPI `api/server.py` 只作为内部调试/受控接口，不作为生产外部入口。
- Go 当前 Worker Pool 业务下载主链属于需要收敛的兼容实现，不扩展为 Python 业务抓取的替代方案。
- Go 与 Python 只通过版本化内部协议协作，不直接互相导入源码。
- MySQL 权威写入由 Go 控制面协调，Python 不直接写权威业务表。

## Consequences

- 所有外部浏览器、CLI 运维入口和 API 集成方统一走 Go 网关。
- `/api/v1`、认证、SSE 和任务状态在 Go 侧形成单一权威。
- Python HTTP 调试接口不得出现在 Nginx 对外暴露路径中。
- 后续迁移必须把业务下载主链收敛到 Python 采集核心，同时保留 Go 的调度协调职责。
- 当前 `api/server.py` 可保留为受控调试能力，但不得被写成生产外部网关。

## Alternatives

- Python FastAPI 作为外部 API：与冻结 PD-031 冲突，不采用。
- Go 继续作为业务抓取主链：与冻结 PD-033 冲突，不采用。
- 双外部网关长期并存：会产生认证、状态、错误和版本协议分裂，不采用。

## Migration

1. 建立 Go OpenAPI 权威契约。
2. 将认证、Session、API Token、SSE 和 `/api/v1` 收敛到 Go。
3. 将 Python 业务抓取链作为正式采集核心，Go 仅负责调度和下载事件协调。
4. 收缩 Python FastAPI 到内部受控端口或本地调试入口。
5. 由 Go 统一消费版本化结果并执行 MySQL 权威写入。
6. 本 BUILD 不修改任何 Go/Python 实现。

## Current Status

- CURRENT_CONFLICT：Python FastAPI 外露、Go Worker 下载主链、Python 历史 MySQL 写入路径
- TARGET_V1：Go 唯一外部业务网关
- production loader 仍为 NOT_STARTED，部署仍为 BLOCKED。

## References

- `docs/PRODUCT_DESIGN_V1.0.md`
- `docs/API_CONTRACT.md`
- `docs/SECURITY_ARCHITECTURE.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- ADR-001、ADR-023、ADR-025
