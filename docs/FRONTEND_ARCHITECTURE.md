# 通用型爬虫 Web 前端架构

本文是 Web 前端目标架构文档。当前 `web/` 不存在，React 未实现；tracked `frontend/index.html` Vue 3 页面分类为 CURRENT_CONFLICT。本文描述目标设计，不代表已完成。

## 1. 当前状态与目标

| 项目 | 当前状态 | 目标状态 |
|---|---|---|
| `web/` | 不存在 | TARGET_V1：React 工程根目录 |
| React | 不存在 | TARGET_V1 |
| TypeScript strict | 不存在 | TARGET_V1 |
| Vite | 不存在 | TARGET_V1 |
| Ant Design | 不存在 | TARGET_V1 |
| TanStack Query | 不存在 | TARGET_V1 |
| Vue 页面 | `frontend/index.html`，CURRENT_CONFLICT | Web V1 实施后替换/归档 |
| OpenAPI types | 不存在 | TARGET_V1，由 Go OpenAPI 生成 |

## 2. 技术约束

- React 管理状态使用 TanStack Query；局部交互使用 React 本地状态。
- API 类型由 OpenAPI generated types 提供，禁止手写与权威 OpenAPI 冲突的重复类型。
- HTTP 使用薄 Axios 客户端，只负责 baseURL、鉴权头、错误归一和 request ID。
- 默认简体中文，保留 i18n 结构。
- 视觉为浅色蓝灰科技管理台，桌面优先。
- 关键界面以 WCAG 2.2 AA 为目标。
- 正式支持 Chrome/Edge 最近两个稳定版；Firefox 执行冒烟测试。

## 3. 建议目录结构

```text
web/
  src/
    app/             应用初始化、路由、错误边界
    api/             Axios client 与 generated types 装配
    auth/            初始化/登录/会话
    components/      通用组件
    features/
      dashboard/
      tasks/
      results/
      sites/
      system/
    i18n/
    styles/
    types/
    hooks/
  openapi/           生成输入与输出（不作为手写业务逻辑）
```

## 4. 路由矩阵

| 路由 | 页面 | 权限 | 当前状态 |
|---|---|---|---|
| `/bootstrap` | 首次管理员初始化 | 无会话且系统未初始化 | NOT_STARTED |
| `/login` | 登录 | 无会话 | NOT_STARTED |
| `/` | Dashboard | 已登录管理员 | NOT_STARTED |
| `/tasks` | 任务列表：服务端分页、状态/站点/时间筛选、排序、进入详情、进入创建任务 | 已登录管理员 | NOT_STARTED |
| `/tasks/new` | 创建任务 | 已登录管理员 | NOT_STARTED |
| `/tasks/:taskId` | 任务详情/进度 | 已登录管理员 | NOT_STARTED |
| `/results` | 结果列表 | 已登录管理员 | NOT_STARTED |
| `/results/:articleId` | 结果详情/审核 | 已登录管理员 | NOT_STARTED |
| `/config/sites` | 站点配置 | 已登录管理员 | NOT_STARTED |
| `/config/plugins` | 插件配置 | 已登录管理员 | NOT_STARTED |
| `/system` | 系统/日志/安全状态 | 已登录管理员，安全状态只读 | NOT_STARTED |

V1 单管理员模式下不引入复杂 RBAC；路由权限只区分“已认证”和“初始化完成”。

## 5. 七大模块

| 模块 | 用户目标 | 主要页面/视图 | 主要字段 | 主要操作 | 当前状态 |
|---|---|---|---|---|---|
| 初始化/登录 | 完成首次管理员初始化并建立会话 | bootstrap、login、logout | username、password、bootstrap_token | 初始化、登录、登出、会话续期提示 | NOT_STARTED |
| Dashboard | 查看系统运行概览 | 总览卡片、任务趋势、队列状态、安全状态入口 | active_tasks、success_rate、queue_lag、storage | 跳转创建任务、查看详情 | NOT_STARTED |
| 创建任务 | 创建并确认采集范围 | 任务表单、范围建议、确认页 | site、keywords、mode、limits、policy_id | 创建草稿、获取建议、确认执行 | NOT_STARTED |
| 任务列表/详情/进度 | 跟踪任务生命周期 | 列表、筛选、详情、阶段进度、SSE实时事件 | task_id、status、stage、progress、event_time | 取消、重试、查看阶段、查看错误 | NOT_STARTED |
| 结果列表/详情/审核/导出 | 查询、审核和导出采集结果 | 结果列表、正文详情、审核表单、导出任务 | article_id、title、url、score、review_status | 审核、通过/驳回、发起异步导出、下载导出结果 | NOT_STARTED |
| 站点与插件配置 | 管理站点能力和插件 | 站点列表/详情、插件列表/详情 | site_code、capabilities、plugin_version、enabled | 启停插件、配置站点、查看审计状态 | NOT_STARTED |
| 系统/日志/只读安全状态 | 查看系统健康和安全状态 | 系统健康、日志检索、只读安全状态 | readiness、level、event_type、evidence_status | 查看、刷新、只读筛选 | NOT_STARTED |

## 6. 页面与交互通用状态

每个数据视图必须实现：

- Empty State：无数据时的引导文案和可执行入口。
- Loading：首次加载骨架屏或受控 Spin，不使用不可见占位。
- Error State：安全错误信息、重试按钮和 request ID。
- Success Feedback：创建/审核/导出等操作成功后给出可理解反馈。
- Danger Confirmation：取消任务、吊销 Token、覆盖配置等危险操作必须二次确认并显示影响。
- Pagination/Filter/Sort：列表由服务端分页、筛选和排序支持。
- Responsive Boundary：桌面优先，宽屏为主要工作台；窄屏不破坏关键操作可发现性。
- Accessibility：焦点顺序、语义标题、对比度、键盘操作和错误提示可达。

## 7. 组件分层

| 层 | 内容 | 责任 |
|---|---|---|
| Feature page | 页面级容器 | 数据获取编排、页面状态 |
| Feature component | 表单、表格、详情面板 | 业务交互 |
| Common component | Ant Design 封装、状态组件 | 复用 UI |
| API/data layer | OpenAPI types + Axios client | 请求、错误归一、缓存键 |

禁止页面组件直接拼接原始 HTTP URL；所有请求必须通过 API layer。
## 8. Query Key 设计

TanStack Query key 必须可追踪、可失效：

| Query Key | 数据 | 失效时机 |
|---|---|---|
| `["session"]` | 当前会话 | 登出、8 小时绝对超时 |
| `["dashboard", "overview"]` | Dashboard 概览 | 页面刷新、任务状态事件 |
| `["tasks", filters]` | 任务列表 | 创建、取消、重试后 |
| `["task", taskId]` | 任务详情 | 任务事件到达后 |
| `["task", taskId, "events"]` | 任务事件 | SSE 或 polling |
| `["results", filters]` | 结果列表 | 审核或导出后 |
| `["article", articleId]` | 结果详情 | 审核后 |
| `["sites"]` | 站点列表 | 站点配置变更后 |
| `["plugins"]` | 插件列表 | 插件启停后 |
| `["system", "health"]` | 系统健康 | 轮询或手动刷新 |
| `["system", "security"]` | 只读安全状态 | 轮询或手动刷新 |

## 9. 表单与校验

- 创建任务表单按 OpenAPI schema 渲染字段和校验规则。
- 危险范围输入在提交前显示任务范围建议。
- 日期/时间使用 UTC 输入并本地化展示。
- 文件上传仅在导出或附件允许的边界内出现。
- 校验错误直接绑定字段，可被屏幕阅读器识别。

## 10. SSE 连接与 Polling 降级

- 事件源使用 `Last-Event-ID` 重连，event_id 单调递增。
- SSE 连接发送 15 秒 heartbeat，前端超时无事件时自动重连。
- SSE 不可用时降级为 5 秒 polling。
- polling 使用 `since_event_id` 或时间游标，避免重复事件。
- 任务事件按 task_id 分发到任务详情和 Dashboard。

## 11. 错误边界与安全

- 顶层 React Error Boundary 捕获渲染异常。
- API 错误统一转换：展示安全消息和 request ID，不显示内部堆栈。
- CSRF token 由同源写请求携带。
- Session/API Token 不写入 localStorage 或可被脚本读取的存储。
- Cookie 使用 HttpOnly、Secure 和合适 SameSite 策略。
- 安全状态页面只读，不展示 secret、token 原文或敏感地址。

## 12. i18n、主题与无障碍

- i18n key 按 feature 分组，默认简体中文。
- 主题使用浅色蓝灰科技管理台，Ant Design token 统一配置。
- 文本不做视口宽度缩放，字号保持稳定。
- 焦点可见性、对比度、标签、错误提示和键盘导航满足 WCAG 2.2 AA。

## 13. 浏览器支持与测试

- 开发目标：Chrome/Edge 最近两个稳定版。
- 冒烟目标：Firefox 最近稳定版。
- 前端测试：Vitest、React Testing Library、Playwright。
- 测试覆盖路由渲染、表单校验、查询状态、SSE/polling 降级、危险操作确认和关键无障碍路径。
- 所有测试不得依赖真实网络或真实 production 服务。

## 14. 性能预算

- 内网首屏目标 ≤ 2.5 秒。
- 路由级 code splitting，Dashboard/任务/结果页面不共享无关注入。
- 列表页服务端分页，禁止前端一次性加载全量数据。
- 大正文详情使用懒加载。

## 15. Vue 残留迁移策略

- `frontend/index.html` 保持 CURRENT_CONFLICT 标签，不作为目标设计依据。
- Web V1 实施时先建立 React 页面和 API 契约。
- 功能等价与验收通过后，再替换或归档 Vue 页面。
- 本 BUILD 不删除 Vue 文件、不安装 npm 依赖、不创建 React 代码。

## 16. 验收入口

- 用户可通过 Web 面板完成登录、创建任务、确认范围、查看进度、审核结果和发起导出。
- 所有页面具备 loading/empty/error/success 状态。
- 安全状态页面只读且不泄露敏感值。
- 关键流程达到 WCAG 2.2 AA 和浏览器兼容目标。
