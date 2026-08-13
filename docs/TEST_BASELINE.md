# TEST_BASELINE.md

## 基线日期

2026-08-13

## 环境

- OS：Windows
- Python：3.14.7
- Python 解释器：`C:\Users\35594\AppData\Local\Programs\Python\Python314\python.exe`
- pip：26.1.2
- pytest：9.1.1
- Go：go1.26.5 windows/amd64

## Python 运行依赖

来自 `requirements.txt`，按发行包名排序：

| 包名 | 版本 | 直接 import 来源 |
|---|---|---|
| beautifulsoup4 | 4.15.0 | `bs4`：crawler/site/analyzer.py、crawler/site/forms.py、plugins/html.py 等 |
| duckdb | 1.5.4 | `duckdb`：storage/manager.py、monitor/report.py 等 |
| fastapi | 0.138.0 | `fastapi`：api/server.py |
| idna | 3.18 | `idna`：crawler/site/normalizer.py |
| lxml | 6.1.1 | `lxml`：crawler/extractor/readability.py |
| openpyxl | 3.1.5 | `openpyxl`：crawler/parser/office.py |
| pydantic | 2.13.4 | `pydantic`：api/server.py |
| PyMySQL | 1.2.0 | `pymysql`：storage/mysql_store.py、tests/integration/conftest.py |
| PyPDF2 | 3.0.1 | `PyPDF2`：crawler/parser/pdf.py |
| python-docx | 1.2.0 | `docx`：crawler/parser/office.py |
| redis | 8.0.1 | `redis`：api/server.py、workers/search_worker.py 等 |
| requests | 2.34.2 | `requests`：httpx/fetch.py |
| urllib3 | 2.7.0 | `urllib3`：httpx/session_pool.py |
| uvicorn | 0.49.0 | `uvicorn`：main.py |

可选第三方模块 `trafilatura` 未安装，但源码在 try/except 中导入并有空字符串回退，因此未纳入必装运行依赖。

## Python 测试依赖

来自 `requirements-dev.txt`：

```text
-r requirements.txt
pytest==9.1.1
```

`pytest` 的直接 import 来源：`tests/integration/conftest.py` 及多个测试文件。

## Python 测试结果

命令：

```powershell
py -m pytest --collect-only -q
py -m pytest -q
```

结果：

- 收集：643 tests
- 通过：636
- 跳过：7
- 失败：0
- 最终实际耗时：3.82s（该次运行的观察值，不作为稳定性能门槛）

TASK-017E-R4 新增 `tests/test_search_probe.py`（61 tests）。

TASK-017E-R5 新增 `tests/test_selector_evidence.py`、`tests/test_probe_formal.py`、`tests/test_probe_formal_json.py`、`tests/test_plan_builder_evidence.py`。

TASK-017E 新增 `tests/test_plan_executor.py`、`tests/test_search_orchestrator.py`。

TASK-017E 缓存语义修复新增 `tests/test_plan_cache_delete.py`、`tests/test_search_orchestrator_cache.py`。

TASK-017E delete 可观察性修复新增 `tests/test_search_orchestrator_delete_observability.py`。

TASK-017F 新增 `tests/test_url_message_contract.py`、`tests/fixtures/url_message_contract.json` 与 `go-spider/internal/queue/url_message_contract_test.go`。Go 契约测试通过 go-redis hook 拦截 BRPOP 并注入 fixture，实际调用 `RedisQueue.PopURL()`，经生产 `pop()` 中的 `json.Unmarshal` 解码为 `HTMLPayload`。

跳过项为 `tests/integration/` 下的 E2E 测试，因未设置 `E2E_ENABLED=1` 自动跳过，不会访问 Redis、MySQL 或外部 HTTP 服务。

具体跳过项：

- `tests/integration/test_all_failed.py:10`、`test_all_failed.py:30`
- `tests/integration/test_empty_search.py:9`、`test_empty_search.py:25`、`test_empty_search.py:44`
- `tests/integration/test_partial_failure.py:10`
- `tests/integration/test_success_pipeline.py:10`


TASK-017F 定向测试结果：

- `tests/test_url_message_contract.py`、`test_plan_cache.py`、`test_plan_cache_delete.py`、`test_plan_executor.py`、`test_search_orchestrator.py`、`test_search_orchestrator_cache.py`、`test_search_orchestrator_delete_observability.py`：87 passed
- `URLMessage or url_message or protocol`：52 passed
- `cache and delete`：9 passed
- `cache and (selector_mismatch or plan_invalid or no_results)`：4 passed
- `publish_failure or no_results`：5 passed

Go 生产解码契约测试：

- `TestPythonURLMessageContractDecodesThroughProductionPopURL`
- `TestPythonURLMessageContractRejectsInvalidJSONThroughProductionPopURL`
- `TestPythonURLMessageContractIsHTMLPayloadStructCompatible`
- `TestPythonURLMessageContractHasNoNestedPayloadOrLegacyTime`
结果：4 passed；BRPOP 与 ProcessHook 各 1 次，DialHook 与 ProcessPipelineHook 各 0 次；非法 JSON 通过生产 `PopURL()` 返回错误。



## Go 离线测试

Go 模块：

- 路径：`go-spider/`
- module：`crawler-platform`
- go.mod 与 go.sum 存在且本轮未修改

命令：

```powershell
$env:GOPROXY = "off"
$env:GOSUMDB = "off"
$env:GOWORK = "off"
go test -mod=readonly -count=1 ./...
go vet -mod=readonly ./...
```

结果：

- crawler-platform：ok
- internal/api：ok
- internal/protocol：ok
- internal/queue：ok
- internal/store：ok
- `internal/store` 存在 3 个 MySQL 跳过测试：
  - `TestUpdateTaskSuccess`
  - `TestUpdateTaskErrorOnInvalidDB`
  - `TestUpdateTaskNonExistentRow`
- 跳过原因：当前离线门禁环境没有可用 MySQL，测试按既有条件跳过
- 没有连接真实 MySQL；跳过不是测试通过；这 3 项不属于 TASK-017 SearchPlan、URLMessage 或生产解码核心范围
- internal/worker：ok
- 无 test files 的包：client、config、httpx
- `go vet -mod=readonly ./...`：通过
- 退出码：0

说明：

- `GOPROXY=off` 禁止下载模块
- `GOSUMDB=off` 禁止校验网络校验和
- `-mod=readonly` 禁止自动修改 go.mod/go.sum
- Go 测试未访问互联网、Redis、MySQL 或真实网站

## 外部访问确认

本轮离线测试未访问：

- 互联网
- 真实政府网站
- Redis
- MySQL
- 其他数据库
- 外部 HTTP 服务
- 外部消息队列

本地 HTTP fixture 仅在 E2E 测试启用时由测试代码启动，本轮未启用。

## 依赖安装状态

本轮未执行：

- pip install / uninstall / upgrade
- go get / go mod tidy / go mod download
- 创建虚拟环境

依赖文件仅记录当前已安装并验证通过的版本。

## 复现命令

```powershell
# Python
py -m pytest --collect-only -q
py -m pytest -q

# Go
Set-Location go-spider
$env:GOPROXY = "off"
$env:GOSUMDB = "off"
$env:GOWORK = "off"
go test -mod=readonly -count=1 ./...
go vet -mod=readonly ./...
```

## 已知限制

- `trafilatura` 为可选依赖，未安装时解析器回退为空字符串
- `openai` 仅在 AI parser 注释示例中出现，当前不是实际 import
- E2E 集成测试需要显式设置 `E2E_ENABLED=1` 并具备 Redis/MySQL 环境，不作为默认离线基线


TASK-018B 新增 `tests/test_search_plan_schema_v2.py`、`tests/test_request_builder.py`、`tests/test_adapter_registry.py` 和 `tests/fixtures/search_plan_schema_v2.json`，并迁移现有 SearchPlan 相关测试到 schema v2。

TASK-018B 产品范围：

- `plan_schema_version=2`，cache envelope schema version=2；
- 新 schema 不含 `query_params/request_body_template`；
- 旧缓存 `incompatible` 不进入 executor，按 cache miss 重建；
- AdapterRegistry 未注册真实 Adapter；
- RequestBuilder 无网络；
- executor 仅单页过渡路径。

TASK-018C–G 尚未完成。


TASK-018C 新增 `tests/test_html_adapter.py` 与 `tests/fixtures/html_adapter_results.html`，覆盖 GET/POST、HTML 解析、零结果、多页、后续页失败和安全 URL 校验。`plan_executor.py` 的 HTML 路径复用正式 HTML Adapter，不再包含重复 HTML parser。

TASK-018D–G 尚未完成。


TASK-018D 新增 `tests/test_trs_adapter.py`、`tests/fixtures/trs_adapter_response.json`、`crawler/search/json_utils.py`、`trs_response_parser.py` 和 `trs_adapter.py`。`plan_executor.py` 的 TRS 路径复用正式 Adapter，并统一使用唯一严格 JSON 解码 helper。

TASK-018E–G 尚未完成。


TASK-018E 新增 `tests/test_jpaas_adapter.py`、`tests/test_legacy_jpaas_plugin.py`、`tests/fixtures/jpaas_adapter_response.json`、`crawler/search/jpaas_parser.py` 和 `jpaas_adapter.py`。`plugins/jpaas.py` 已机械提取共享解析核心并保持 legacy 输出不变。

TASK-018F 已完成；TASK-018G 已实现。


TASK-018F 新增 `tests/test_generic_json_adapter.py`、`tests/test_json_pointer.py`、`crawler/search/json_pointer.py`、`generic_json_response_parser.py` 和 `generic_json_adapter.py`。`plan_executor.py` 已移除内联 JSON 解析并改为四类 Adapter 分派。

TASK-018G 已实现；TASK-018H 最终交付门禁已完成。


TASK-018G 新增 `tests/test_production_registry.py` 与 `tests/test_production_adapter_pipeline.py`，并扩展 `tests/test_plan_builder.py`；覆盖默认 Registry 组合、Registry 精确分派、executor 注入、六类离线生产链、缓存/发布语义和零网络约束。

TASK-018G 产品范围：

- `crawler/search/adapter_composition.py` 提供 `build_default_adapter_registry()`；
- `plan_executor.py` 的 `RegistryPlanExecutor`/`execute_plan_with_registry()` 只通过 Registry 分派；
- `search_orchestrator.py` 与 `workers/search_worker.py` v2 生产路径接入默认 Registry；
- `plan_builder.py` 支持显式 generic_json Candidate；
- SearchPlan/cache/plan_id/Redis key/TTL/fingerprint、外部消息协议、错误码、Go 和 legacy 均未修改。

TASK-018H 最终交付门禁已完成；等待人工 pre-push 审查。


TASK-018H 最终交付门禁新增/更新测试：

- 四类 Adapter 的 allowed path prefix 路径边界测试；
- Generic JSON 禁用分页单页执行测试；
- JSON 分页与固定模板、页码与页大小冲突测试；
- JPAAS malformed nested 类型测试；
- `default_v2_components` 与 worker v2 production Registry 测试。

TASK-018H 最终基线：643 collected / 636 passed / 7 skipped / 0 failed。
Go 全量 test/vet、compileall、pip check、git diff --check 均通过。
TASK-018 正式关闭等待人工 pre-push 审查；TASK-022 残余风险仍存在。
