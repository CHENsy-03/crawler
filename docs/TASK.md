# TASK.md
本文件只描述当前正在执行的任务。
当前只能启用一个任务，不得同时混入其他重构、修复或功能开发。
执行本任务前必须先阅读项目根目录的 AGENTS.md。

1. 任务基本信息
项目	内容
任务名称	确定 Go/Python 运行时职责边界
任务编号	TASK-003
任务类型	fix
优先级	P0
当前状态	completed
开始日期	2026-07-27
前置任务	TASK-002
负责人	待执行
执行工具	Codex / PowerShell
目标项目	workspace/crawler
目标分支	当前工作分支
后续任务	TASK-002：修复基础契约和已确认的明显错误

2. 任务背景
workspace/crawler 正在进行 Python 与 Go 通用采集平台升级。
在开始基础契约修复、HTTP能力统一、标准数据模型建设、搜索插件开发、浏览器后备探测、采集流水线串联、Go任务调度和前端改造之前，必须先确认当前项目的真实运行状态和测试状态。
目前尚未形成经过实际命令验证的基线，不能确定：
Python项目是否能够正常导入；
Python主程序是否能够正常启动；
Python测试是否能够被发现和执行；
Go正式服务是否能够编译；
Go测试是否能够通过；
Go静态检查是否存在问题；
当前依赖声明是否完整；
当前配置是否足以支持本地运行；
哪些失败是已有问题；
哪些失败可能由后续修改引入。
因此，本任务只负责检查、执行和记录现状，不进行业务功能修改。
3. 当前问题
当前项目缺少一份可核对的运行与测试基线记录。
需要通过读取真实代码、检查项目结构并执行真实命令，回答以下问题：
Python使用什么版本；
Python依赖由哪些文件声明；
Python程序的正式入口是什么；
Python程序最小启动命令是什么；
Python现有测试数量和分布是什么；
Python测试当前通过、失败和跳过数量是多少；
正式Go服务能否编译；
Go测试当前通过或失败情况是什么；
go vet 当前是否通过；
哪些测试依赖 MySQL、Redis、网络或其他外部服务；
当前运行是否缺少配置、依赖或环境变量；
当前已有失败的根因和影响范围是什么。
4. 任务目标
本任务必须完成以下可验证目标：
确认项目根目录和正式Go服务目录；
记录当前Git工作区状态；
记录Python版本；
识别Python依赖声明文件；
识别Python程序入口和启动方式；
收集Python测试文件和测试数量；
执行Python测试基线；
记录Python测试真实结果；
记录Go版本；
确认正式Go服务为 workspace/crawler/go-spider；
执行Go测试基线；
执行Go静态检查基线；
在环境允许时检查Go编译状态；
区分代码失败、依赖失败、配置失败和外部服务失败；
记录所有实际执行的命令和真实输出摘要；
不修改业务代码；
给出下一任务建议，但不在本任务内实施。
5. 允许检查的范围
本任务允许读取和检查：
项目根目录文件；
Python源码；
Python测试；
Python依赖声明；
Python配置加载方式；
Python启动入口；
workspace/crawler/go-spider；
Go源码；
Go测试；
go.mod；
go.sum；
示例配置；
启动脚本；
Docker相关配置；
README和现有项目文档；
Git状态和Git差异。
本任务允许执行：
只读目录检查；
Python版本检查；
Python导入检查；
Python测试收集；
Python测试；
Go版本检查；
Go测试；
Go静态检查；
Go编译检查；
不会修改业务数据的最小启动检查。
6. 非目标
本任务不负责：
修复搜索逻辑；
修改HTML解析逻辑；
修改PDF或Office解析逻辑；
实现网站自动探测；
实现SearchSpec；
引入Playwright或Chromium；
统一HTTP客户端；
调整Python与Go职责；
修改Python与Go通信协议；
修改任务状态机；
修改Redis队列设计；
修改MySQL表结构；
创建数据库迁移；
修改前端功能；
重构目录结构；
删除旧模块；
合并历史项目；
修改 workspace/go-spider；
进行生产部署；
执行真实网站压力测试。
7. 本任务禁止行为
执行TASK-001期间禁止：
为了让测试通过而修改业务代码；
删除、跳过或弱化失败测试；
安装未经确认的关键依赖新版本；
修改数据库结构；
修改公共API或JSON字段；
修改Python与Go通信契约；
修改采集流水线；
修改搜索业务逻辑；
默认启动浏览器探测；
修改前端；
大规模格式化代码；
移动或重命名目录；
修改独立项目 workspace/go-spider；
使用破坏性Git命令；
自动提交或推送代码；
将“未执行”记录为“通过”；
隐藏已有失败；
将环境问题直接认定为代码缺陷；
将代码缺陷伪装成环境问题；
在未核对真实输出时填写测试结果。
8. 实施顺序
必须按以下顺序执行：
读取AGENTS.md
→ 读取TASK.md
→ 确认当前目录
→ 检查Git状态
→ 检查项目目录
→ 识别Python入口和依赖
→ 识别Python测试
→ 记录Python环境
→ 执行Python基线测试
→ 识别正式Go服务
→ 记录Go环境
→ 执行Go基线测试
→ 执行Go静态检查
→ 检查最小运行条件
→ 分类所有失败
→ 检查Git差异
→ 更新执行记录
→ 输出基线报告
9. 基线检查命令

以下命令只是计划命令。

执行人员必须根据真实目录、项目文件和操作系统确认后再运行，不得把计划命令预先记录为已执行。

9.1 项目和Git状态
Get-Location
git status --short
git branch --show-current
Get-ChildItem -Force
9.2 Python环境
python --version
python -m pip --version

根据真实依赖文件检查：

Get-ChildItem -Recurse -File |
    Where-Object {
        $_.Name -in @(
            "requirements.txt",
            "requirements-dev.txt",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            "poetry.lock"
        )
    } |
    Select-Object FullName
9.3 Python测试收集
python -m pytest --collect-only -q
9.4 Python测试基线
python -m pytest -q

如果项目已有并已配置对应工具，才考虑执行：

python -m ruff check .
python -m mypy .

不得仅为TASK-001临时引入未使用的质量工具。

9.5 Go环境

进入正式Go服务目录：

cd .\go-spider
go version
go env GOMOD

必须确认 go env GOMOD 指向：

workspace\crawler\go-spider\go.mod

不得进入：

workspace\go-spider
9.6 Go测试和静态检查
go test ./...
go vet ./...

如果需要检查编译，可执行：

go build ./...

go test -race ./... 仅在当前环境支持并且有必要时执行；未执行时必须记录原因。

10. 测试记录要求

每条实际执行的命令都必须记录：

执行时间；
执行目录；
完整命令；
退出码；
通过数量；
失败数量；
跳过数量；
关键输出摘要；
是否依赖外部服务；
失败分类；
是否属于已有问题。

禁止只记录：

测试正常
全部通过
运行没问题
11. 失败分类

发现的问题必须至少按以下类别记录：

分类	含义
code	当前代码自身错误
dependency	Python包或Go模块缺失、冲突或版本不兼容
configuration	配置文件、配置项或环境变量缺失
infrastructure	MySQL、Redis、文件服务等基础设施不可用
network	网络、DNS、TLS或外部网站不可用
test	测试代码、测试数据或测试隔离存在问题
platform	操作系统、权限或工具链问题
unknown	证据不足，暂时无法确定

不得在证据不足时直接给出确定性根因。

12. 最低检查场景
正常场景
Python解释器可用；
Python测试可以被收集；
Python测试可以启动；
Go模块可以被识别；
Go测试可以启动；
go vet 可以启动；
正式Go服务目录识别正确。
边界场景
没有任何Python测试；
某些测试被跳过；
某些模块没有被测试覆盖；
配置文件存在但配置值缺失；
测试命令成功但未发现测试；
Go包存在但没有测试文件。
异常场景
Python依赖缺失；
Python导入失败；
Python测试收集失败；
MySQL不可用；
Redis不可用；
外部网络不可用；
Go模块下载失败；
Go编译失败；
Go测试失败；
go vet 失败；
启动入口不存在；
配置文件路径错误。
兼容性场景
不改变现有HTTP路径；
不改变现有JSON字段；
不改变命令行参数；
不改变配置名称；
不改变数据库结构；
不改变任务状态；
不改变Python与Go职责边界。
13. 验收标准

TASK-001只有在以下条件全部满足后才能标记为 completed：

 已确认项目根目录；
 已确认正式Go服务目录；
 已记录修改前Git状态；
 已识别Python版本；
 已识别Python依赖声明；
 已识别Python程序入口；
 已识别Python测试分布；
 已执行Python测试收集；
 已执行Python基线测试或记录不能执行的明确原因；
 已记录Python测试真实结果；
 已识别Go版本；
 已确认正确的 go.mod；
 已执行Go测试或记录不能执行的明确原因；
 已执行 go vet 或记录不能执行的明确原因；
 已执行Go编译检查或记录未执行原因；
 已分类现有失败；
 已记录外部服务依赖；
 已确认未修改业务代码；
 已执行任务结束前Git检查；
 已填写完整执行记录；
 已给出明确的下一任务建议。

如果存在未满足项，不得将状态改为 completed。

14. 执行记录

执行日期：2026-07-27
执行环境：
- Windows PowerShell 7.6.4
- Python 3.14.4
- pytest 9.1.1
- Go 1.26.5 windows/amd64
- Git 分支：chore/crawler-test-baseline

执行结果：
1. python -m pytest --collect-only -q
   - 成功收集6个测试
   - 退出码：0

2. python -m pytest -q
   - 6 passed in 0.38s
   - 退出码：0

3. python .\main.py --help
   - CLI入口加载成功
   - 退出码：0

4. python .\main.py --self-test
   - 执行失败
   - 错误：NameError: name ''extract_content'' is not defined
   - 位置：main.py 的 run_self_test()
   - 退出码：1

5. go test ./...
   - 编译失败
   - internal/queue/redis.go:60:13：HTMLPayload不存在Title字段
   - internal/queue/redis.go:68:13：HTMLPayload不存在Error字段
   - 退出码：1
   - 当前项目未发现任何 *_test.go，尚无实际Go测试用例

6. go vet ./...
   - 因相同的HTMLPayload字段错误失败
   - 退出码：1

7. go build ./...
   - 因相同的HTMLPayload字段错误失败
   - 退出码：1

基线结论：
- Python现有6个pytest测试全部通过。
- Python CLI帮助入口通过。
- Python内置自检失败，确认存在extract_content导入缺失。
- main.py的URL模式还存在filter_by_score导入缺失。
- Go模块可以被go list识别，但当前无法完成编译。
- Go项目尚无测试文件，不能认定Go测试覆盖通过。
- 项目当前没有Python依赖声明文件。
- TASK-001只负责建立和记录基线，本任务不修改业务代码。

14.1 开始信息
项目	实际结果
开始时间	2026-07-27
执行人员	Codex
当前目录	E:\\AI_Projects\\Codex\\workspace\\crawler
当前分支	chore/crawler-test-baseline
初始Git状态	M monitor/__pycache__/report.cpython-314.pyc; ?? AGENTS.md; ?? docs/
Python版本	3.14.4
Go版本	1.26.5 windows/amd64
14.2 项目入口和依赖
检查项	实际结果
Python入口	main.py (CLI)
Python依赖文件	无 (无requirements.txt/pyproject.toml等)
Python测试目录	tests/
正式Go服务目录	go-spider/
Go模块文件	go-spider/go.mod
必需配置	config/site.json, http.json, score.json, system.json
外部服务依赖	MySQL, Redis, 网络(TRS/JPAAS API)
14.3 实际执行命令
序号	执行目录	命令	退出码	结果摘要
1	crawler	python -m pytest -q	0	6 passed
2	crawler	python .\\main.py --help	0	CLI OK
3	crawler	python .\\main.py --self-test	1	extract_content未定义
4	go-spider	go test ./...	1	HTMLPayload字段缺失
5	go-spider	go vet ./...	1	同test
6	go-spider	go build ./...	1	同test
14.4 Python测试结果
项目	实际结果
收集数量	6
通过数量	6
失败数量	0
错误数量	0
跳过数量	0
未执行项目	ruff/mypy（未配置）
失败摘要	无
14.5 Go检查结果
项目	实际结果
go test ./...	失败（编译错误）
通过包数量	0
失败包数量	8
go vet ./...	失败（同test）
go build ./...	失败（同test）
go test -race ./...	未执行（编译阻塞）
失败摘要	HTMLPayload结构体缺少Title和Error字段
14.6 问题记录
编号	分类	位置	现象	证据	影响	是否阻塞后续
BASE-001	code	main.py:run_self_test()	extract_content未定义	python --self-test 退出码1	内置自检不可用	否
BASE-002	code	go-spider:internal/queue/redis.go	HTMLPayload字段缺失	go test 退出码1	Go无法编译	是
BASE-003	code	main.py:discover	filter_by_score未定义	import缺失	URL模式不可用	否
BASE-004	dependency	项目根目录	无依赖声明文件	ls无requirements.txt	无法复现环境	否
14.7 实际修改文件
当前预期只允许修改：docs/TASK.md
实际修改文件：docs/TASK.md（仅本节）
14.8 未执行检查
ruff、mypy：项目未配置，未执行
go test -race：Go编译阻塞，未执行
go test --count=1：未执行
网站连通性测试：不触发
14.9 兼容性结果
未修改任何命令行参数、配置字段、HTTP路径、JSON结构
14.10 剩余风险
Python内置自检不可用，URL爬取模式可能受影响
Go项目无法编译需修复HTMLPayload后再测试15. 任务结束前检查

结束前必须执行：

git status --short
git diff --stat
git diff

并确认：

没有修改业务代码；
没有修改数据库结构；
没有修改公共接口；
没有修改配置名称；
没有修改Python与Go职责；
没有修改 workspace/go-spider；
没有删除测试；
没有隐藏失败；
没有写入敏感信息；
所有测试结果均来自真实命令输出。
16. 完成后的汇报格式

完成TASK-001后必须按以下结构汇报：

1. 完成结果
2. 检查和修改的文件
3. Python运行基线
4. Python测试基线
5. Go运行基线
6. Go测试和静态检查基线
7. 实际执行的命令
8. 失败和阻塞项
9. 未执行内容及原因
10. 兼容性影响
11. 数据库和配置影响
12. 遗留问题
13. 建议的下一步

不得使用没有真实证据的“全部正常”或“全部通过”。

17. 任务关闭

只有全部验收标准满足后，才允许：

将任务状态从 pending 更新为 completed；
填写完成日期；
保留完整执行记录；
提出后续独立任务；
等待用户确认后再进入下一任务。

【TASK-002 已转为正式任务，见第 18 节】




## 18. TASK-002：修复基础契约和已确认的明显错误

### 18.1 任务目标

修复 TASK-001 基线测试确认的基础错误，使相关模块能够正常导入、编译并通过最小回归测试。

### 18.2 修复范围

1. 修复 Python extract_content 导入问题。
2. 修复 Python filter_by_score 导入问题。
3. 统一 Go HTMLPayload 与 Redis 消费代码之间的字段契约。
4. 为上述问题添加最小回归测试。

### 18.3 已确认问题

#### Python

- extract_content 的定义位置与实际导入路径不一致。
- filter_by_score 的定义位置与实际导入路径不一致。

#### Go

使用 HTMLPayload 的代码读取了以下字段，但当前结构体没有对应定义：

- Title
- Error

这会导致 Go 项目编译失败。

### 18.4 明确不包含

本任务不处理：

- 通用站点自动发现；
- 四川财政等具体网站适配；
- 搜索架构重构；
- Redis/MySQL/DuckDB 架构调整；
- 未经确认的依赖升级；
- go.mod、go.sum 大范围整理；
- 与本次失败无关的格式化或重构。

### 18.5 验收标准

- Python 目标模块可正常导入。
- Python 最小回归测试通过。
- HTMLPayload 与生产者、消费者字段一致。
- go test ./... 不再因 Title 或 Error 字段缺失而失败。
- 不引入与 TASK-002 无关的依赖变化。
- 所有修复均有对应执行记录。

### 18.6 执行记录

已完成以下修改：

1. 在 main.py 补充 xtract_content 导入。
2. 在 main.py 补充 ilter_by_score 导入。
3. 为 Go HTMLPayload 增加 Title、Error、Score 字段。
4. 修复 go-spider/internal/worker/pool.go 中被前序编译错误掩盖的遗留导入问题。
5. 添加 Python 导入契约回归测试。
6. 添加 Go JSON 消息契约回归测试。

验证结果：

- python -m pytest -q：8 passed
- go test ./...：全部通过
- go vet ./...：全部通过
- go.mod、go.sum：未修改
- 	ask-001-go-deps.patch：未应用、未提交


## 19. TASK-003：确定 Go/Python 运行时职责边界

### 19.1 任务目标

调查当前 Go、Python 两套运行时的入口、调用链、重复模块、Redis 消息协议和存储写入关系，确定后续通用爬虫升级的唯一职责边界。

本任务只形成架构决策和迁移约束，不删除或重构现有业务代码。

### 19.2 调查结果

当前系统存在以下正式入口：

- Go CLI：go-spider/main.go
- Go API：go-spider/main.go --api
- Python CLI：main.py
- Python API：pi/server.py
- Python Worker：parser/redis_worker.py

当前存在以下重复能力：

- 搜索；
- HTTP 客户端；
- API 服务；
- 配置加载；
- MySQL 存储；
- Redis 队列访问。

Python 独有且应继续由 Python 负责的能力：

- HTML 正文解析；
- Readability 抽取；
- PDF 解析；
- 关键词评分和过滤；
- URL、内容去重；
- DuckDB 本地存储。

### 19.3 最终职责决策

#### Go 负责

1. 正式 CLI 和 API 入口。
2. 任务创建、状态管理和编排。
3. Redis 队列管理。
4. 高并发 HTTP 下载。
5. 重试、限流、超时和下载错误管理。
6. MySQL 最终结果写入。
7. 运行状态和监控指标汇总。

#### Python 负责

1. 搜索源适配和 URL 发现。
2. TRS、JPAAS、普通 HTML 搜索插件。
3. HTML 正文解析和 Readability 抽取。
4. PDF 解析。
5. 关键词扩展、评分和过滤。
6. URL 与内容去重。
7. DuckDB 本地分析和缓存。
8. 作为 Redis Worker 执行内容处理任务。

### 19.4 运行时通信边界

Go 与 Python 不直接互相导入或调用对方源码，通过 Redis JSON 消息交换任务和结果。

目标队列包括：

- crawler:search
- crawler:url
- crawler:html
- crawler:result
- crawler:error

所有消息必须：

- 使用明确的 JSON 字段；
- 包含协议版本；
- 包含任务 ID；
- 支持错误信息；
- 具有对应的 Go 和 Python 契约测试。

### 19.5 存储写入权

- MySQL 最终业务数据：由 Go 写入。
- DuckDB 本地分析和缓存：由 Python 写入。
- Redis：Go 管理任务生命周期，Python 只消费或生产协议允许的消息。
- Python MySQL 写入模块暂时保留，后续迁移完成后再下线。

### 19.6 本任务不包含

- 删除 Python FastAPI；
- 删除 Python CLI；
- 删除任意重复模块；
- 修改 Redis 队列；
- 调整生产者或消费者；
- 应用依赖补丁；
- 执行 go mod tidy；
- 实现通用站点自动发现。

### 19.7 验收结果

- 已定位 Go、Python 全部运行入口。
- 已定位 Redis 队列生产者和消费者。
- 已定位两端重复模块。
- 已确定目标职责矩阵。
- 已确定 Redis 为跨运行时通信边界。
- 未修改业务代码和依赖文件。

### 19.8 状态

completed

## 20. TASK-008：端到端集成验收

### 20.1 任务目标

在本地 Docker 环境中完成整条采集流水线的端到端集成验证，确认全部消息协议、消费者协程和存储写入符合设计。

本任务只做集成验证和必要修复，不扩展新业务功能。

### 20.2 验证范围

```
API 创建任务 → crawler:search → Python Search Worker → crawler:url
→ Go 下载 Worker → crawler:html → Python Parser Worker → crawler:result
→ Go Result Consumer → MySQL Article → API 查询任务最终状态
```

### 20.3 验证场景

| 场景 | 预期状态 | 关键断言 |
|------|----------|----------|
| 全部成功 | completed | Stored == Expected |
| 部分 URL 失败 | completed_with_errors | Stored > 0, Failed > 0 |
| 全部 URL 失败 | failed | Stored == 0, Failed > 0 |
| 搜索无结果 | completed | Expected == 0 |

### 20.4 额外验证项

- Redis 各队列（crawler:search/url/html/result/event/error）最终清空
- MySQL Article 字段完整且 URL 幂等
- 同一错误重复消费不会重复增加 Failed
- 服务重启后不会产生重复文章
- Parser 只有一个正式消费者
- 所有 Consumer 都能优雅停止
- API 不会在结果入库前提前返回 completed

### 20.5 测试文件

```
tests/integration/
├── __init__.py
├── test_success_pipeline.py
├── test_partial_failure.py
├── test_all_failed.py
└── test_empty_search.py
```

### 20.6 环境要求

- Docker Desktop 或兼容容器运行时
- 通过 docker-compose 启动 Redis + MySQL
- Python 依赖：redis, pymysql
- Go 编译：支持 -mod=mod

### 20.7 验收标准

- 四条场景全部验证通过
- 额外验证项全部确认
- 未修改业务协议和数据库结构
- tests/integration/ 新增文件全部提交

### 20.8 状态

completed



## TASK-011

### 问题说明
Python Parser Worker 输出 YYYY-MM-DD 格式的 publish_date，但 Go consumeResult 只使用 time.RFC3339 解析，解析错误被静默忽略，零值日期被替换为 time.Now()，导致缺失或非法发布日期被伪造成抓取时间。

### 修改内容
1. store/mysql.go：Article.PublishTime 从 time.Time 改为 *time.Time。
2. worker/pool.go：新增 parsePublishTime 函数，优先解析 YYYY-MM-DD，兼容 RFC3339；空字符串返回 nil；非法值返回 nil+error。
3. consumeResult 使用 parsePublishTime 替代直接 time.Parse，不再回退到 time.Now()。
4. 新增 8 个测试覆盖全部日期输入场景。

### 验收结果
- go test ./internal/worker/：28 passed
- go test ./...：全包通过
- go vet./...：无错误
- python -m pytest -q：35 passed, 7 skipped
- git diff --check：无错误

### 状态
completed


## TASK-012：文档状态与空残留文件清理

### 背景
- TASK-008 已完成但状态过期（仍为 in_progress）。
- TASK-011 存在空重复标题。
- task-001-go-deps.patch 是无内容的历史残留文件。

### 范围
- 修正 TASK-008 状态为 completed。
- 删除重复 TASK-011 标题。
- 删除空 patch。

### 范围外
- Python/Go 职责收敛。
- SYSTEM_ARCHITECTURE.md 内容更新。
- 业务代码、依赖和测试逻辑修改。
- 远程分支管理。

### 验收结果
- TASK-008 为 completed。
- TASK-011 只有一个标题。
- TASK-012 只有一个标题。
- 空 patch 已删除。
- 无业务代码变化。
- git diff --check 通过。

### 状态
completed


## TASK-013：实现文章查询接口

### 实现内容
- 实现 Go API GET /articles 端点，从 MySQL 查询并返回真实文章数据。
- 支持 keyword 查询参数过滤（透传给 GORM title LIKE 查询）。
- 支持 limit 参数，默认 100，上限 1000。
- 非法 limit（非数字、0、负数、超过 1000）返回 HTTP 400，且不调用数据库查询。
- 参数校验优先于数据库可用性检查。
- 查询失败返回 HTTP 500，且不泄露内部错误。
- 数据库不可用时（纯 nil 接口或 typed nil *store.MySQLStore）返回 HTTP 503。
- 空结果返回 articles: []（非 null）。
- 新增 articleQuerier 最小接口，解耦 API 与具体 MySQLStore。
- 新增 13 个 API handler 测试，覆盖正常查询、关键词过滤、limit 校验、空结果、查询错误、数据库不可用、typed nil、参数校验优先级等场景。

### 验收结果
- internal/api：13/13 PASS
- go test ./...：通过
- go vet ./...：通过
- go build ./...：通过
- Python：35 passed, 7 skipped

### 关联信息
- PR #6
- PR URL：https://github.com/CHENsy-03/Codex/pull/6
- 功能提交：9cd9f31
- 合并提交：fde72d2

### 状态
completed


## TASK-014：实现通用 HTML 搜索插件

### 目标
实现 plugins/html.py，使配置为 search.type: "html" 的站点能够请求普通 HTML 搜索结果页，解析搜索结果，并按现有插件协议输出统一结果。

### 实现范围
1. 读取站点 HTML 搜索配置（search.api_url、search.params）。
2. 构造关键词搜索 GET 请求。
3. 支持 max_pages 分页，且不超过配置页数。
4. 将相对 URL 转换为绝对 URL。
5. 提取 title、url、snippet。
6. 过滤空链接和无效链接。
7. 对结果 URL 去重，保持首次出现顺序。
8. 与现有插件调用协议兼容。
9. 不影响 TRS 和 JPAAS 搜索。

### 关于自动发现
- 有限策略：当 api_url 未配置时，尝试 site.base_url + 常见搜索路径（如 /search、/s）。
- 不承诺支持任意搜索表单、POST 表单、JavaScript 搜索或验证码。
- 复杂自动发现应留给后续独立任务。

### 验收标准
- search.type 为 html 且 api_url 有效配置时能返回结果。
- 结果至少包含 title、url、snippet。
- 正确处理相对链接。
- 支持 max_pages，且不超过配置页数。
- 重复 URL 只保留一次。
- 空结果页返回空列表而不是异常。
- 非 2xx、超时或页面结构不匹配时遵循现有插件错误协议。
- 使用本地 HTTP 测试服务或 HTTP mock，不访问真实政府网站。
- HTML 插件单元测试通过。
- 现有 TRS、JPAAS 测试不回归。
- Python 全量测试通过。
- Go 全量测试、vet、build 通过。

### 允许修改
- workspace/crawler/plugins/html.py
- workspace/crawler/tests/test_html_plugin.py
- workspace/crawler/config/site.json（仅在确需配置示例时）

### 仅经代码证明必需后才可修改
- workspace/crawler/plugins/__init__.py
- workspace/crawler/crawler/search/detector.py

### 范围外
- Go 功能修改
- 前端
- 数据库结构
- Redis 队列
- JS 动态页面
- Playwright/Selenium
- POST 搜索表单
- 验证码和登录
- 搜索引擎辅助发现
- 任意网站完全自动识别
- TRS/JPAAS 重构
- 远程分支清理
- 修改全部代码.txt

### 实现结果
- 完成普通 HTML 搜索结果页的配置化 GET 请求。
- 支持关键词参数、分页上限和相对 URL 转换。
- 支持无效链接过滤、跨页 URL 去重和空结果。
- 支持配置化解析及有限搜索端点发现。
- 新增 9 个使用 HTTP Mock 的单元测试，不访问真实网站。
- 未修改 TRS、JPAAS、Go、数据库、Redis 和前端。

### 验收结果
- HTML 插件新增测试：9/9 通过。
- Python 全量测试：44 passed, 7 skipped。
- go test ./... -count=1：通过。
- go vet ./...：通过。
- go build ./...：通过。
- PR #8 仅包含 plugins/html.py 和 tests/test_html_plugin.py。

### 关联信息
- PR #8
- https://github.com/CHENsy-03/Codex/pull/8
- 功能提交：5f02aa0
- 合并提交：830c8b6
- 完成日期：2026-07-29

### 状态
completed


## TASK-015：建立 URL + 关键词 v2 任务契约与运行时 SearchPlan 模型

### 基本信息
- 状态：pending
- 创建日期：2026-07-31
- 类型：架构与协议
- 优先级：P0
- 本任务只定义后续代码实施范围，不在本分支实施业务代码。

### 背景证据
1. Python CLI、Go CLI、Go API 当前均以预配置 `site/site_key` 为核心。
2. Redis `SearchMessage v1` 只有 `site`、`keyword`、`level`、`max_pages`，不能表达未知网站的 `target_url`。
3. 当前协议版本只有 `1.0`。
4. 目前没有可序列化的运行时 `SearchPlan`。
5. `detector.py` 和 `planner.py` 尚未接入正式 Search Worker。
6. 插件仍从静态 `site.json` 获取搜索配置。
7. TASK-014 的 HTML 插件不等于“URL + 关键词”的自动发现闭环。

### 任务目标
1. 定义 Go CLI、Go API 的 `target_url + keywords[]` 输入契约。
2. 定义 Go/Python 一致的 Redis v2 envelope 和 `SearchRequested v2`。
3. 定义可序列化的 `SearchPlan`、`SearchHit` 及必要枚举和校验规则。
4. 明确 v1 `site/profile` 兼容模式和显式版本分派。
5. 建立 Go/Python 共用的 canonical JSON v2 fixture。
6. 建立两端序列化、反序列化、校验及字段语义一致性测试。
7. 为 TASK-016 网站分析和 TASK-017 运行时计划生成提供稳定契约。

### SearchPlan 定义范围
至少覆盖：
- `plan_id`、协议版本、生命周期状态。
- 搜索策略。
- endpoint 和 HTTP method。
- query 参数或请求体模板。
- 分页规则。
- 搜索结果及正文选择器。
- 域名和采集边界。
- 发现证据及置信度。
- 创建来源、创建时间和失效信息。

最终字段命名应在代码实施时遵循现有项目风格，但 Go/Python 字段语义必须完全一致。

### 兼容与校验规则
- 新入口支持 `target_url`。
- 旧 `site/profile` 模式暂时保留。
- `--url` 与 `--site` 的互斥或组合规则必须明确。
- 禁止静默推断协议版本。
- `target_url` 只接受 `http` 和 `https`。
- 非法 URL、空关键词、全空白关键词、重复关键词和冲突参数必须有确定行为。
- v1 fixture、v1 消息和现有流程必须继续通过回归测试。

### 非目标
- 不实现完整 Site Analyzer。
- 不实现搜索表单或接口自动发现。
- 不实现选择器自动推断。
- 不接入四川、山东或其他单一站点。
- 不实现 HTML POST、通用 JSON/XHR 或浏览器后备。
- 不重构全部插件。
- 不迁移数据库。
- 不下线 v1。
- 不修改前端。
- 不治理 TASK.md 历史结构。
- 不实施 TASK-016 或 TASK-017。

### 预计代码实施范围
```text
workspace/crawler/go-spider/main.go
workspace/crawler/go-spider/internal/api/handler.go
workspace/crawler/go-spider/internal/protocol/messages.go
workspace/crawler/go-spider/internal/protocol/messages_test.go
workspace/crawler/protocol/messages.py
workspace/crawler/protocol/__init__.py
workspace/crawler/crawler/search/search_plan.py（拟新增）
workspace/crawler/tests/fixtures/redis_protocol_v2.json（拟新增）
workspace/crawler/tests/test_redis_protocol.py
workspace/crawler/docs/REDIS_PROTOCOL.md
workspace/crawler/docs/SYSTEM_ARCHITECTURE.md
workspace/crawler/docs/TASK.md
```

`workspace/crawler/workers/search_worker.py` 仅在“完成最小 v2 消息接收”确有必要且能提供代码证据时，才允许在实施阶段修改；本次文档分支不修改它。

### 验收标准
1. Go/Python 可读取同一 v2 fixture，字段语义一致。
2. `target_url` 仅接受 `http/https`。
3. 空关键词、非法 URL 和冲突参数返回明确错误。
4. `SearchPlan` 可稳定序列化、反序列化并产生确定性标识。
5. v1 profile 流程及现有测试继续通过。
6. v1/v2 使用显式协议版本分派。
7. Python 全量测试通过。
8. Go `test`、`vet`、`build` 通过。
9. `git diff --check` 通过。
10. 未引入单站点配置、复杂自动发现、数据库迁移或浏览器能力。

### 停止条件
- 最新代码出现与本定义冲突的 v2 设计。
- 必须破坏 v1 才能继续。
- Go/Python 字段语义存在需要用户决定的冲突。
- 必须迁移数据库或重命名现有 Redis 队列。
- 实际修改范围明显超出 TASK-015。
- 用户预存文件发生变化。

### 任务关系
- TASK-014 提供配置驱动的 HTML 搜索能力。
- TASK-015 只建立 URL 契约、v2 协议和 SearchPlan 模型。
- TASK-016 才实现网站分析和搜索入口发现。
- TASK-017 才实现运行时 SearchPlan 生成、校验、缓存及正式 Worker 接入。
- downloader 和单站点问题不得取代通用化主线。
