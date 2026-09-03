# ADR-023: React、TypeScript 与 Vite 作为 Web 前端基线

**状态：** Accepted
**日期：** 2026-09-03
**关联：** PD-011、PD-012、PD-013、PD-014、PD-015、PD-016；TASK-020A

## Context

产品主入口是 Web 管理面板，但当前 repository 内只有 `frontend/index.html` 的 Vue 3 CDN 仪表盘，没有 `web/`、React 工程、TypeScript 工程或 Vite 工程。Vue 页面是历史残留，分类为 CURRENT_CONFLICT，不承担目标产品入口职责。

## Decision

目标 Web 前端基线固定为：

- React
- TypeScript strict
- Vite
- Ant Design
- TanStack Query 服务端状态管理
- React 本地状态用于局部交互
- OpenAPI generated types
- 薄 Axios 客户端

前端代码未来位于 `web/`，目标页面包括初始化/登录、Dashboard、创建任务、任务列表/详情/进度、结果列表/详情/审核/导出、站点与插件配置、系统/日志/只读安全状态七大模块。

## Consequences

- 后续前端任务必须以 React + TypeScript strict + Vite 创建工程。
- 前端不得依赖 Vue、jQuery、全局 CDN 或非生成型 API 手写类型。
- API 类型必须由 Go OpenAPI 权威生成，前端不维护第二套接口类型权威。
- 当前 `frontend/index.html` 仍保留，待 Web V1 实施任务替换，不在本设计阶段删除。
- 产品文档、任务文档和实现中不得再把 Vue 描述为目标前端。

## Alternatives

- Vue 3：当前历史残留，与冻结 PD-011 冲突，不采用。
- 不使用框架或全局 CDN：无法满足多页面管理台、可维护状态和 WCAG 目标，不采用。
- Next.js 等 SSR 框架：V1 是内部单机部署的桌面优先管理台，Vite SPA 更贴合当前范围，不采用。

## Migration

1. 在 Web V1 实施任务中创建 `web/` React 工程。
2. 按 OpenAPI 生成 types 并建立薄 Axios 客户端。
3. 以新 React 页面覆盖七大模块。
4. 经独立验收确认功能覆盖后，再移除或归档 `frontend/index.html` Vue 残留。
5. 本 BUILD 不删除 Vue、不创建 React 代码、不安装 npm 依赖。

## Current Status

- CURRENT_CONFLICT：`frontend/index.html` Vue 3 残留
- TARGET_V1：React + TypeScript strict + Vite + Ant Design
- 当前 React 未实现，本文是目标设计，不是完成证明。

## References

- `docs/PRODUCT_DESIGN_V1.0.md`
- `docs/FRONTEND_ARCHITECTURE.md`
- `docs/API_CONTRACT.md`
- PD-011 至 PD-030
