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
- 状态：completed
- 创建日期：2026-07-31
- 类型：架构与协议
- 优先级：P0
- 代码实施已在隔离 worktree 分支 `feat/task-015-v2-contract` 完成并验证。

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

### 实施结果
- 新增共用 canonical fixture：`workspace/crawler/tests/fixtures/redis_protocol_v2.json`。
- Python 全量测试：105 passed, 7 skipped。
- Go `test ./...`：exit 0。
- Go `vet ./...`：exit 0。
- Go `build ./...`：exit 0。
- `git diff --check`：exit 0。
- v2 envelope、`SearchRequested`、`SearchPlan`、`SearchHit` 已在 Go/Python 双端实现并保持一致。
- 空集合统一输出 `{}`/`[]`，不输出 `null`。
- `level`/`max_pages` 可选，默认分别为 0/1；缺失版本、未知字段、跨版本字段均返回明确错误。
- `target_url` 拒绝前后空白、非法端口、缺失 host 和畸形 IPv6 authority。
- `keywords` 必须是 JSON 数组且每个元素必须是字符串，JSON `null` 元素一律拒绝；v1 `site/keyword` 必须为非空字符串；整数字段显式 `null` 拒绝；v1 `site/profile` 互斥；CLI 输入错误先于任何 Redis 资源创建；畸形 IPv6 统一返回 `INVALID_TARGET_URL`。
- `plan_id` 使用稳定 canonical JSON（键排序、紧凑分隔符、UTF-8）的 SHA-256 十六进制摘要；U+2028/U+2029 转义为 `\u2028`/`\u2029`，`<>&` 不转义；运行时状态与时间字段不参与计算。

### 任务关系
- TASK-014 提供配置驱动的 HTML 搜索能力。
- TASK-015 只建立 URL 契约、v2 协议和 SearchPlan 模型。
- TASK-016 才实现网站分析和搜索入口发现。
- TASK-017 才实现运行时 SearchPlan 生成、校验、缓存及正式 Worker 接入。
- downloader 和单站点问题不得取代通用化主线。


## TASK-016：实现网站分析器与搜索候选发现

### 16.1 基本信息

| 项目 | 内容 |
|---|---|
| 任务编号 | TASK-016 |
| 任务名称 | 实现网站分析器与搜索候选发现 |
| 任务类型 | feature / security |
| 优先级 | P0 |
| 当前状态 | pending |
| 定义日期 | 2026-08-02 |
| 前置任务 | TASK-015（已通过 PR #11 合入 main） |
| 后续任务 | TASK-017（SearchPlan 生成、验证、缓存及 Worker v2 接入） |
| 唯一工作目录 | E:\AI_Projects\Codex\workspace\crawler |
| 执行工具 | Codex / PowerShell |

本任务必须在上述唯一项目目录中执行，不得创建新 worktree、项目副本或其他工作区。

本节只完成 TASK-016 的任务定义。状态保持 pending；在定义通过独立审查前，不得实施源码、暂存、提交、推送或创建 PR。

### 16.2 当前基线与事实来源

以下内容是定义时的参考基线，实施前必须在唯一项目目录重新核验，不得把历史报告替代真实 Git 和测试输出：

- TASK-015 已合入 main，参考 HEAD 为 d128a592e56d533e819b4dec24f1311707c3ebec。
- TASK-015 已建立 Go/Python v2 输入契约、SearchRequested、SearchPlan、SearchHit 和确定性 plan_id。
- TASK-016 尚未实施，也尚未接入正式 Search Worker。
- 参考 Python 基线为 105 passed、7 skipped。
- 参考 Go 基线为 go test、go vet、go build 均 exit 0。
- 当前正式 Search Worker 仍按 v1 site_key → config/site.json → plugin 执行。
- 当前 downloader 默认自动跟随重定向，尚无逐跳请求前安全校验能力。

实施前必须记录：

- 当前分支和 HEAD；
- git status --short；
- 暂存区；
- 未跟踪文件；
- Python 和 Go 的真实基线；
- 与本任务允许文件重叠的用户预存修改。

用户已有删除项、未跟踪 DOCX、全部代码汇总文件和备份文件均不属于 TASK-016，不得删除、恢复、暂存或提交。

### 16.3 真实代码审计结论

定义阶段已根据 TASK-015 后的代码确认：

1. crawler/search/detector.py 中的 SiteDetector 只获取入口页，并对页面字符串和少量 Header 进行 CMS 特征加权；它不分析 form、link、script、meta，不做请求前地址策略，也不生成 SearchCandidate。
2. crawler/search/planner.py 中的 QueryPlanner 只生成关键词扩展层级，不是 SearchPlanBuilder。
3. main.py::discover_site 仍是独立旧调试逻辑：直接使用 session.get 探测固定路径、猜测 TRS 配置并打印结果；它绕过正式 Analyzer，也没有完整安全边界。
4. plugins/html.py、plugins/trs.py 和 plugins/jpaas.py 是搜索执行适配器，不是网站分析器。
5. plugins/html.py 的 _SEARCH_PATHS 当前未被 search() 用于路径探测；_discover_search_url 只从配置或 base_url 解析 endpoint。
6. workers/search_worker.py 仍只读取 v1 site、keyword，并通过 site.json 选择插件，不消费 v2 target_url。
7. crawler/search/search_plan.py 已存在 SearchPlan/SearchHit 模型和校验，但没有 Analyzer 自动生成逻辑。
8. httpx/fetch.py 使用 requests.Session.get；未显式关闭自动重定向，因此重定向可能在策略检查前已被访问。
9. 当前 downloader 没有发现阶段统一的最大响应字节、Content-Type、重定向次数和流式中止能力。
10. 未发现已经实现但未记录的 TASK-016 能力。

如果实施前最新代码与以上任一事实不符，必须先暂停，更新本定义或报告冲突，不得按过期假设编码。

### 16.4 唯一目标和数据流

TASK-016 只实现以下闭环：

~~~text
target_url
  → URL 规范化
  → 最低请求前安全预检
  → 安全获取入口页
  → 静态 HTML 分析
  → SearchCandidate
  → evidence / diagnostics
~~~

本任务只回答“入口页上有哪些可能的搜索入口，以及为什么认为它们是候选”。

本任务不回答：

- 候选是否真的能完成搜索；
- 搜索结果结构是什么；
- 使用什么选择器或分页规则；
- 哪个候选足以生成或执行 SearchPlan。

### 16.5 明确非目标

TASK-016 不得实施：

- 候选搜索请求或探测验证；
- 使用用户关键词提交 GET 或 POST 搜索；
- 搜索结果选择器推断；
- 分页推断或第二页验证；
- 置信度评分和高置信度自动执行；
- SearchPlan 生成、校验、执行或缓存；
- Search Worker v2 接入；
- Redis 消息、队列或协议修改；
- Go 代码修改；
- 数据库、迁移、存储或前端修改；
- HTML/TRS/JPAAS 执行适配器重构；
- site.json 写入或单站点配置；
- JavaScript 执行；
- Playwright、Selenium、Chromium 或浏览器后备；
- 登录、验证码、付费墙或访问控制绕过；
- 真实外部网站自动化测试或压力测试；
- TASK-018、TASK-019、TASK-020、TASK-022 或 TASK-023 的能力。

### 16.6 Python 内部模型

SearchCandidate 与 SiteAnalysisResult 均为 Python 内部模型。

它们不得加入 TASK-015 的 Go/Python 跨语言协议，不得修改 SearchPlan、SearchHit、SearchDiscovery 或相关枚举。

#### 16.6.1 SearchCandidate

SearchCandidate 至少包含：

| 字段 | 要求 |
|---|---|
| method | 仅表达静态页面声明的 GET 或 POST；不得因此发起请求 |
| endpoint | 由 form/action 或静态线索解析出的绝对 http/https URL |
| keyword_param | 推断出的关键词字段名；不能包含关键词值 |
| fixed_params | 仅保留公开、非敏感、长度受限的固定参数 |
| request_encoding | 可选；只描述 form-urlencoded 等静态声明 |
| source | form、trs_signature、jpaas_signature、internal_link、static_script、meta 或 common_path 等内部来源 |
| priority | 用于确定性排序的内部优先级 |
| scope | same_origin 或 requires_scope_validation 等内部范围结论 |
| evidence | 有界、脱敏、可测试的证据摘要 |
| status | 只能表达 unverified 或 requires_scope_validation 等未验证状态 |

严格要求：

- 所有返回 Candidate 均未经探测验证。
- status 不得使用 ready、active、validated、executable 或任何会与 SearchPlan 生命周期混淆的值。
- POST Candidate 只表示“页面声明了可能的 POST 搜索表单”，不得提交。
- 跨域 endpoint 不得静默提升为普通同域 Candidate；只能拒绝或标记 requires_scope_validation。
- Candidate 不得携带完整 HTML、Cookie、Authorization、Session、Token、密码、CSRF 值、签名值或可复用认证材料。
- Candidate 不得携带用户实际关键词。

Candidate 的稳定去重键至少由 method、规范化 endpoint、keyword_param 和排序后的公开 fixed_params 组成。

#### 16.6.2 SiteAnalysisResult

SiteAnalysisResult 至少包含：

- normalized_url；
- final_url 或安全停止前最后一个已验证 URL；
- candidates；
- diagnostics；
- 有限 fetch 摘要：状态码、Content-Type、读取字节数、重定向次数；
- analyzer_version。

SiteAnalysisResult 不得包含：

- 完整页面 HTML；
- 完整响应 Header；
- Set-Cookie；
- Cookie jar；
- Authorization；
- 敏感查询值；
- 表单秘密值；
- 原始脚本全文。

如果目标 URL 自身包含 token、session、auth、password、signature 等敏感查询字段，必须在请求前按策略拒绝或使用不暴露值的结构化诊断；不得把秘密值复制到结果、日志或 evidence。

#### 16.6.3 诊断结构

每条诊断至少包含：

- code；
- stage；
- message；
- severity；
- retryable；
- 有界且脱敏的 details。

网络失败和“成功分析但没有候选”必须是两种不同结果。

### 16.7 URL 规范化

规范化函数必须是无网络、确定性、可单元测试的纯逻辑。

必须：

- 只接受字符串类型的 http/https URL；
- 不静默 strip；前后空白直接返回 INVALID_TARGET_URL；
- 拒绝控制字符和 URL 内部非法空白；
- 拒绝空 host；
- 拒绝 userinfo，包括 username、password 和 user@host；
- 拒绝空端口、非法端口、越界端口和畸形 IPv6 authority；
- 将 scheme 和 hostname 转为小写；
- 规范化合法 IDN hostname 的 ASCII 表达，失败则拒绝；
- 移除 http:80 和 https:443 默认端口；
- 移除 fragment；
- 保留可能有语义的 path、query、重复 query 键和顺序；
- 空 path 规范化为 /；
- 不在本任务中擅自删除跟踪参数或重排 query。

TASK-015 的 validate_target_url 仍保持共享协议的语法校验语义；TASK-016 可以在发现层增加更严格的安全规范化，但不得回写或改变 TASK-015 契约行为。

### 16.8 请求前安全策略

每次真实请求前都必须执行：

1. URL 规范化。
2. host 解析。
3. 全部解析地址分类。
4. 范围和重定向策略校验。
5. 仅在全部结果安全时发出该次请求。

默认拒绝：

- loopback；
- private；
- link-local；
- multicast；
- unspecified；
- reserved；
- 云 metadata 地址；
- IPv6 本地地址；
- IPv4-mapped IPv6 映射出的不安全 IPv4；
- 任何解析结果中混入上述地址的域名。

安全要求：

- IP literal 必须直接分类，不能绕过 DNS 检查。
- DNS 返回多个地址时，只要一个地址不安全，整个目标即拒绝。
- 不得依赖反向 DNS 证明目标安全。
- resolver、transport 和安全策略必须可显式注入测试。
- 生产默认策略不得放行 localhost。
- 不得设置隐藏的 test_mode、环境变量或 hostname 特例绕过生产策略。
- 被策略拒绝时 downloader 调用次数必须为 0。

TASK-016 只建立最低 SSRF 门禁。DNS rebinding、连接级 IP pinning、完整域名 allowlist/denylist、租户策略和安全可观测性属于 TASK-022；这些残余风险必须在实现报告中明确记录，不得宣称已完成生产级 SSRF 防护。

### 16.9 安全重定向与 downloader 硬门禁

Analyzer 禁止调用当前默认自动重定向的 fetch 行为。

实施时只能采用以下两种路径之一：

1. 向后兼容地增加“单次 GET、不自动跟随重定向、可流式读取”的 downloader 能力，由 Analyzer 自己执行受限重定向循环；或
2. 如果无法在最小范围内安全实现，立即停止 TASK-016，并先定义独立 downloader 安全前置任务。

不得采用：

- 自动跟随完成后再检查 response.url；
- Analyzer 直接调用 requests、Session.get 或新建第二套 HTTP 客户端；
- 在 main.py、detector.py 或插件中旁路统一 downloader；
- 关闭 TLS 校验；
- 先请求后校验；
- 通过捕获异常后返回空 Candidate 隐藏安全失败。

受限重定向循环必须：

- 只处理明确允许的 301、302、303、307、308；
- 单次请求能力必须把 3xx 和 Location 原样交给 Analyzer，不得在底层把它吞成普通失败；
- 在读取下一跳 Location 后使用当前 URL 安全解析相对地址；
- 在下一次请求前重新执行完整规范化、DNS/IP 和范围校验；
- 检测缺失/非法 Location；
- 检测循环；
- 执行集中配置的最大重定向次数；
- 对 hostname 或 origin 变化执行默认拒绝策略；
- 最多允许同 host 的 http → https 安全升级，不允许 https → http 降级；
- 在第二跳指向私网时，保证第二次网络调用尚未发生。

发现阶段的自动重试必须关闭，或明确限制为同一个已经校验的 URL；不得在底层重试过程中改变目标、跟随重定向或隐藏新的请求目的地。

新增 downloader 能力必须是可选、向后兼容的；现有 fetch、post_json、get_json 和插件行为默认保持不变。

### 16.10 入口页获取和资源限制

TASK-016 只对经过安全检查的入口 URL 发起 GET。

所有限制必须集中在可注入、可测试的 DiscoveryLimits 或等价配置模型中，不得散落 Magic Number。

至少包含：

| 限制 | 要求 |
|---|---|
| connect/read timeout | 有界，失败返回 FETCH_FAILED |
| max_redirects | 达到上限后返回 REDIRECT_BLOCKED |
| max_response_bytes | 流式读取中达到上限立即停止 |
| allowed_content_types | 默认只允许静态 HTML/XHTML |
| max_forms | 超限后确定性截断并诊断 |
| max_inputs_per_form | 防止恶意大表单 |
| max_candidates | 去重和排序后执行硬上限 |
| max_script_chars | 限制单个及总静态脚本文本分析量 |
| max_links_meta | 限制 link、a、meta 线索量 |
| max_common_paths | 常见路径候选的固定上限 |
| max_evidence_items / chars | 防止结果和日志膨胀 |

响应大小必须同时处理：

- Content-Length 已超过上限时，在读取正文前停止；
- 缺少或伪造 Content-Length 时，在流式读取累计达到上限后停止；
- 压缩响应按实际解压后进入分析器的字节上限控制；
- 不允许先完整下载到内存再检查大小。

Content-Type 不允许时返回 UNSUPPORTED_CONTENT_TYPE，不得尝试把 PDF、Office、图片或任意二进制内容当作入口 HTML 分析。

### 16.11 静态线索分析

静态分析只处理已经安全获取且大小受限的入口 HTML。

#### 16.11.1 搜索表单

必须分析：

- form action；
- method，缺失时按 HTML 语义视为 GET；
- enctype；
- input、select、textarea 的 name/type；
- submit 文本；
- label、placeholder、aria-label；
- hidden 固定参数。

关键词字段识别应使用集中、可测试的名称和语义规则，不得只硬编码单一 q。

公开 hidden 参数可以保留，例如 siteCode、websiteid、serviceId 等站点标识；敏感名称规则优先于公开规则。

以下字段或等价变体不得进入 Candidate、日志或 evidence：

- csrf；
- xsrf；
- token；
- session；
- auth；
- password；
- passwd；
- cookie；
- signature；
- secret；
- nonce；
- captcha；
- verify_code。

依赖敏感临时值的表单必须拒绝复用并产生 SENSITIVE_FORM_REJECTED。

以下表单不得识别为搜索：

- 登录；
- 注册；
- 订阅；
- 留言；
- 上传；
- 支付；
- 修改资料；
- 密码重置；
- 验证码；
- 具有明显写操作或副作用的表单。

GET 表单可以生成未验证 Candidate。

POST 仅允许对明确的 application/x-www-form-urlencoded 搜索表单生成未验证 Candidate；本任务绝不提交。multipart、文件上传或副作用不明的 POST 表单只产生诊断。

#### 16.11.2 CMS 和静态资源线索

至少支持静态识别：

- TRS 特征；
- JPAAS 特征；
- 站内搜索链接；
- a、script、link、meta 中有限的 search、query、jsearch、so、ss 等线索；
- 有界的内联脚本文本 URL/参数名线索；
- 有限常见搜索路径候选。

严格边界：

- 不执行 JavaScript；
- 不解释任意脚本业务逻辑；
- 不加载外部 script、CSS、iframe 或其他资源；
- 不发送 XHR/fetch；
- 不逐个探测常见路径；
- CMS 特征只生成 Candidate 和 evidence，不能直接宣布发现成功；
- base、form action 或链接解析后的跨域 URL必须拒绝或标记待范围验证；
- 站点地图和栏目页可以作为 evidence，但本任务不抓取它们。

### 16.12 Candidate 排序、去重和诊断优先级

排序必须确定，不能依赖 set、dict 偶然顺序或解析器内部地址。

默认来源优先级：

1. 明确 GET 搜索 form；
2. GET form + 公开 hidden 固定参数；
3. 明确 POST form-urlencoded 搜索 form；
4. TRS/JPAAS 特征；
5. 站内搜索链接；
6. 静态 script/link/meta 线索；
7. 有限 common_path 候选。

同优先级使用 method、规范化 endpoint、keyword_param 和固定参数规范化表示作稳定次序。

去重必须在截断前完成；相同去重键只保留优先级最高且 evidence 合并后仍受上限约束的 Candidate。

失败与空结果的诊断必须确定：

| code | 语义 |
|---|---|
| INVALID_TARGET_URL | URL 语法、scheme、authority 或端口不合法 |
| TARGET_BLOCKED_BY_POLICY | 请求前地址或目标策略拒绝 |
| FETCH_FAILED | 入口页网络请求失败；不得伪装为空 Candidate |
| REDIRECT_BLOCKED | 下一跳在请求前被拒绝、Location 非法、循环或超过跳数 |
| RESPONSE_TOO_LARGE | 入口响应在流式读取中达到上限 |
| UNSUPPORTED_CONTENT_TYPE | 入口响应不是允许的静态 HTML 类型 |
| NO_SEARCH_CANDIDATE | 页面成功获取和分析，但没有候选 |
| LOGIN_OR_CAPTCHA_REQUIRED | 页面或表单要求登录、授权或验证码 |
| UNSUPPORTED_JS_SEARCH | 搜索入口只能通过 JavaScript 动态获得 |
| SENSITIVE_FORM_REJECTED | 搜索形态依赖敏感临时值或具有副作用 |

同一页面可以返回多个非致命诊断，但必须有稳定顺序。致命的 URL、安全、重定向、网络、大小和类型错误发生后不得继续静态分析。

### 16.13 预计允许修改范围

实施前必须基于最新代码重新列出精确文件；没有代码证据不得扩大。

预计新增：

~~~text
workspace/crawler/crawler/site/__init__.py
workspace/crawler/crawler/site/models.py
workspace/crawler/crawler/site/normalizer.py
workspace/crawler/crawler/site/security.py
workspace/crawler/crawler/site/forms.py
workspace/crawler/crawler/site/signatures.py
workspace/crawler/crawler/site/analyzer.py
workspace/crawler/tests/test_site_normalizer.py
workspace/crawler/tests/test_site_security.py
workspace/crawler/tests/test_site_forms.py
workspace/crawler/tests/test_site_analyzer.py
workspace/crawler/tests/test_discovery_fetch.py
workspace/crawler/tests/fixtures/site_discovery/
~~~

预计最小修改：

~~~text
workspace/crawler/crawler/search/detector.py
workspace/crawler/crawler/search/__init__.py
workspace/crawler/main.py
workspace/crawler/docs/TASK.md
~~~

其中：

- detector.py 只能成为新 Analyzer 的兼容薄封装，不得保留第二套发现算法。
- SiteDetector.analyze 和 auto_configure 的现有调用签名及兼容返回键必须保留；如代码证明确需弃用，必须先单独定义兼容和下线任务。
- main.py --discover 只能调用同一 Analyzer，并输出脱敏分析结果；不得继续维护固定路径探测和 site.json 配置生成逻辑。
- crawler/search/__init__.py 只允许做必要导出，不得修改 TASK-015 模型。
- docs/TASK.md 只允许在实施完成后填写本任务执行记录和状态。

仅当代码证明安全单次请求无法在现有接口上实现时，条件允许修改：

~~~text
workspace/crawler/crawler/core/downloader.py
workspace/crawler/crawler/core/__init__.py
workspace/crawler/httpx/fetch.py
workspace/crawler/httpx/__init__.py
workspace/crawler/tests/test_core.py
workspace/crawler/tests/test_main_imports.py
workspace/crawler/docs/SYSTEM_ARCHITECTURE.md
workspace/crawler/README.md
~~~

其中代码修改只能增加向后兼容的单次不自动重定向、流式受限 GET 能力，不得改变现有调用方的默认行为。文档只在最新内容尚未描述 Analyzer/Candidate 边界或 --discover 调试行为时同步，不得借机整理无关章节。

### 16.14 禁止修改范围

本任务禁止修改：

~~~text
workspace/crawler/go-spider/
workspace/crawler/protocol/messages.py
workspace/crawler/crawler/search/search_plan.py
workspace/crawler/workers/search_worker.py
workspace/crawler/plugins/html.py
workspace/crawler/plugins/trs.py
workspace/crawler/plugins/jpaas.py
workspace/crawler/plugins/__init__.py
workspace/crawler/config/site.json
workspace/crawler/config/schema.sql
workspace/crawler/storage/
workspace/crawler/frontend/
workspace/crawler/全部代码.txt
~~~

也禁止：

- 修改 TASK-001 至 TASK-015 历史正文；
- 修复现有 TASK.md 控制字符或整理历史结构；
- 改动 Redis 队列、消息版本或 SearchPlan 枚举；
- 新增单站点配置；
- 引入大型依赖；
- 生成或提交缓存、编译产物、DOCX、聚合源码或备份文件；
- 修改用户预存文件；
- 自动暂存、提交、推送或创建 PR。

### 16.15 实施顺序

必须逐步执行：

1. 在唯一项目目录读取全部适用 AGENTS.md、DEVELOPMENT_RULES.md、SYSTEM_ARCHITECTURE.md、REDIS_PROTOCOL.md 和本 TASK。
2. 核对分支、HEAD、工作区、暂存区、未跟踪文件和用户预存修改。
3. 重新审计所有相关定义和调用方。
4. 运行并记录 Python、Go test/vet/build 和 git diff --check 基线。
5. 列出精确修改文件及理由，确认没有越过禁止范围。
6. 先增加 URL、安全、重定向和敏感数据失败测试。
7. 实现内部模型和集中资源限制。
8. 实现纯 URL 规范化和地址策略。
9. 实现或获得安全单次 downloader 能力；如果门禁失败，停止。
10. 实现表单、CMS 和静态线索提取。
11. 实现 Analyzer 编排、确定性排序、去重和诊断。
12. 将 SiteDetector 和 main.py --discover 收敛为同一 Analyzer 的薄入口。
13. 运行专项测试和 Python 全量测试。
14. 运行 Go test、go vet、go build，证明跨语言契约未回归。
15. 执行 git diff --check、git status、暂存区和未跟踪文件检查。
16. 只填写真实执行记录；保持未暂存，等待独立代码审查。

不得同时并行修改多个互相依赖的阶段，以免在安全前置能力尚未通过时继续扩展 Analyzer。

### 16.16 专项测试矩阵

全部自动化测试必须使用 Mock、固定 HTML 或显式注入 resolver/transport；不得访问真实外网。

#### URL 规范化

- scheme/host 大小写；
- 默认端口；
- fragment；
- 空 path；
- path/query 保留；
- 重复 query；
- 前后空白；
- 非 http/https；
- userinfo；
- 空/非法/越界端口；
- 畸形 IPv6；
- 控制字符；
- IDN 成功和失败。

#### 地址策略

- IPv4/IPv6 loopback；
- private；
- link-local；
- multicast；
- unspecified；
- reserved；
- metadata；
- IPv4-mapped IPv6；
- 安全单地址；
- 多地址全部安全；
- 多地址中任一不安全；
- IP literal。

关键断言：所有不安全目标在 downloader 调用前失败，调用次数为 0。

#### 重定向

- 同 host http → https；
- https → http 降级；
- 安全入口 → 私网；
- 安全入口 → metadata；
- 跨 host；
- 相对 Location；
- Location 缺失或非法；
- 重定向循环；
- 最大跳数。

关键断言：重定向至不安全地址时，在第二次请求前停止。

#### 入口响应

- Content-Length 预先超限；
- 无 Content-Length 的流式超限；
- 错误 Content-Type；
- 空 HTML；
- 畸形但可容错 HTML；
- 连接失败、超时和受控 HTTP 错误；
- 重定向响应能够由 Analyzer 读取而不会被底层自动吞掉。

#### Candidate

- GET form；
- GET form + 公开 hidden 参数；
- 相对 action；
- POST form-urlencoded；
- multipart/file 表单；
- TRS 特征；
- JPAAS 特征；
- 站内搜索链接；
- script/link/meta 静态线索；
- 有限 common_path；
- 重复 Candidate；
- 超过候选、form、input、script 和 evidence 上限。

关键断言：

- POST 调用次数为 0；
- common_path 请求次数为 0；
- CMS 特征不产生 ready SearchPlan；
- Candidate 排序和去重在重复运行中完全一致。

#### 边界与敏感数据

- 无搜索入口；
- 登录页；
- 验证码页；
- JS-only 空壳；
- 订阅、留言、支付、上传和密码表单；
- csrf/token/session/auth/password/cookie/signature/nonce 字段；
- 敏感值同时出现在 HTML、Candidate、diagnostics 和日志检查样例中。

关键断言：

- 网络失败不是 NO_SEARCH_CANDIDATE；
- 敏感字段值不出现在结果、日志或 evidence；
- 登录/验证码和 JS-only 返回各自稳定诊断；
- 分析失败不抛出未处理异常。

#### 回归

- TASK-015 SearchPlan round-trip；
- plan_id 确定性；
- v1/v2 Redis fixture；
- 现有 HTML/TRS/JPAAS 插件测试；
- SiteDetector 兼容入口；
- main.py --discover 只调用 Analyzer；
- Python 全量测试；
- Go test、go vet、go build；
- git diff --check。

### 16.17 验收标准

只有以下条件全部满足，TASK-016 才能标记 completed：

- target_url 规范化行为确定且测试完整。
- 不安全目标在任何网络调用前被拒绝。
- 每个重定向目标都在下一跳请求前重新校验。
- Analyzer 未使用默认自动重定向路径。
- 响应大小在流式读取过程中受限。
- 只分析允许的静态 HTML Content-Type。
- GET、公开 hidden、POST、TRS、JPAAS、链接、静态脚本和 common_path 候选均有测试。
- 所有 Candidate 均明确为未经探测验证，不可执行。
- 未生成 SearchPlan，未修改 TASK-015 枚举或 plan_id。
- 未提交 POST，未执行 JavaScript，未启动浏览器。
- 未探测 common_path，未写 site.json。
- 网络失败、空候选、登录/验证码和 JS-only 语义严格区分。
- 敏感字段和值未进入 Candidate、SiteAnalysisResult、diagnostics、evidence 或日志。
- 排序、去重和诊断输出确定。
- SiteDetector 和 main.py --discover 不再维护独立发现算法。
- 所有新增测试不访问真实外网。
- Python 全量测试通过。
- Go test、go vet、go build 通过。
- git diff --check 通过。
- Git 差异只包含经批准的 TASK-016 文件。
- 暂存区为空，未提交、未推送、未创建 PR。
- 用户预存修改保持不变。

参考基线只能用于比较；最终报告必须填写真实命令、退出码和通过/失败/跳过数量。

### 16.18 强制停止条件

出现任一情况立即停止，不得扩大范围或用不安全降级继续：

- 无法在请求前可靠关闭自动重定向。
- 必须先访问 URL 才能完成安全判断。
- 必须绕过统一 downloader。
- 必须修改 TASK-015 协议、SearchPlan 或 plan_id。
- 必须修改 Go、Redis、数据库、Worker 或搜索执行插件。
- 必须执行 JavaScript、启动浏览器或提交候选表单。
- 必须写入 site.json 或新增单站点配置。
- 需要生产级 DNS pinning 才能满足当前实现声明。
- 现有基线测试失败且原因未查明。
- 用户预存修改与目标文件重叠，无法安全区分。
- 实际所需文件明显超出允许范围。
- 最新代码与任务定义冲突。
- 发现敏感值可能进入结果或日志但无法在本任务范围内消除。

停止报告必须说明：

- 阻断步骤；
- 代码证据；
- 已修改文件；
- 测试状态；
- Git 状态；
- 是否产生额外变化；
- 建议的最小前置任务。

不得把停止写成 completed。

### 16.19 回滚原则

TASK-016 不涉及数据库迁移、Redis 状态、site.json 或外部持久化，因此回滚应只涉及本任务代码和测试。

回滚要求：

- 新增模块可整体移除；
- downloader 新能力必须是附加接口，移除后现有默认行为不变；
- detector.py 和 main.py 的兼容改动必须能独立反向应用；
- 不使用 git reset --hard、git clean、整仓 restore 或其他可能覆盖用户修改的命令；
- 只按精确差异反向修改 TASK-016 文件；
- 回滚后重新运行原有 Python/Go 基线；
- 不删除用户文件、聚合代码、备份或未跟踪文档。

### 16.20 任务关系

任务边界固定为：

| 任务 | 职责 |
|---|---|
| TASK-015 | 共享 target_url/keywords 输入和 SearchPlan/SearchHit 契约 |
| TASK-016 | 安全获取入口页并静态发现未经验证的 SearchCandidate |
| TASK-017 | 探测 Candidate、推断选择器/分页、生成和验证 SearchPlan、缓存并接入 Worker v2 |
| TASK-018 | 统一 Adapter，并覆盖 HTML GET/POST、TRS、JPAAS、通用 JSON 的正式执行 |
| TASK-022 | 生产级 SSRF、连接级地址绑定、域名策略、安全指标、告警和审计 |
| TASK-023 | JS-only 浏览器后备可行性评审；未批准前不实施 |

TASK-016 完成不代表“输入任意网站即可自动采集”已经完成。只有 TASK-017 之后才可能形成最小 URL + 关键词搜索闭环，TASK-020 通过后才可宣称完成未知站点 MVP 验收。

### 16.21 定义阶段记录

- 当前状态：pending。
- 本次只向 docs/TASK.md 追加 TASK-016 定义。
- 未实施 TASK-016 源码、测试、fixture 或配置。
- 未实施 TASK-017、TASK-018、TASK-022 或浏览器后备。
- 未修改 Go、Redis、数据库、Worker、插件或 site.json。
- 未暂存、未提交、未推送、未创建 PR。
- 下一步：对本定义进行独立审查；通过后才允许发布定义文档，再单独启动代码实施。
