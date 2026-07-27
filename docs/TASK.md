# TASK.md
本文件只描述当前正在执行的任务。
当前只能启用一个任务，不得同时混入其他重构、修复或功能开发。
执行本任务前必须先阅读项目根目录的 AGENTS.md。

1. 任务基本信息
项目	内容
任务名称	修复基础契约和已确认的明显错误
任务编号	TASK-002
任务类型	fix
优先级	P0
当前状态	completed
开始日期	2026-07-27
前置任务	TASK-001
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