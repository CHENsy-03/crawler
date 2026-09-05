# ADR-026: Opaque ULID Identifier Contract

**状态：** accepted

**日期：** 2026-09-05

**关联：** DEV-004 Fix B3；V1.0 §12.1；API_CONTRACT

## 决策背景

V1.0 §12.1 要求所有业务主键使用不透明 UUID/ULID 或等价稳定标识，避免泄露自增规模，并允许审计表使用内部单调 ID。当前候选 DDL 仍以 BIGINT UNSIGNED AUTO_INCREMENT 作为多数实体主键，不能满足不透明要求。

联合基线只规定 UUID/ULID 类别，没有固定具体实现格式；项目所有者在本 ADR 中裁决 21 类非审计实体统一使用 canonical ULID 文本，AuditLog 作为唯一例外继续使用 MySQL 内部自增 ID。

## ULID 选择理由

- ULID 是 26 字符 Crockford Base32 文本，可直接作为 JSON string 输出，不需要 Base64 或二进制转换。
- ULID 带时间前缀，可按创建顺序粗排序；但时间部分不代替 created_at/persisted_at 等业务时间字段。
- ULID 的 128 bit 熵满足跨服务、跨进程稳定不透明标识要求。
- 相比 UUID 文本，ULID 更短且可排序；相比 BINARY(16)，ULID 避免 API/DB 编码转换。
- 相比 AUTO_INCREMENT，ULID 不泄露实体数量或创建速率。

## 21 类 ULID 实体清单

Admin、Session、APIToken、IdempotencyRecord、CrawlTask、TaskAttempt、TaskStage、TaskEvent、SearchCandidate、FetchArtifact、Article、ArticleVersion、TaskArticle、ReviewDecision、ExportJob、Site、Plugin、OutboxEvent、DeadLetter、Checkpoint、GlobalBlockEntry。

## AuditLog 唯一例外

- 主键：`audit_log_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT`。
- 仅限 MySQL 内部单调标识。
- 不通过公开 API 返回。
- 不作为公开资源 ID。
- 不因业务实体删除而级联删除。
- request_id、event_id、actor_id、resource_id 按各自契约保存，不等于 AuditLog 主键。

## DB 类型与 canonical 格式

21 类非审计实体主键：

- 类型：`CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL`
- canonical 文本：长度精确 26，仅大写 Crockford Base32
- 合法字符：`0123456789ABCDEFGHJKMNPQRSTVWXYZ`
- 禁止字符：I、L、O、U
- 无实体前缀、无连字符、无花括号
- 不接受小写 canonical 表示
- 结构：前 48 bit 为 Unix epoch milliseconds，后 80 bit 为密码学安全随机数

所有引用这些主键的外键列必须使用相同类型、长度、CHARACTER SET 与 COLLATE；nullable 只由关系语义决定。

## 生成边界

- ULID 由 Go MySQL 权威写入协调者在 INSERT 前生成。
- 不使用 MySQL UUID()、触发器或默认表达式生成。
- Python 正式服务不得生成并直接写入 MySQL。
- 同一进程、同一毫秒内必须使用 monotonic 生成。
- DEV-004 只实现数据模型与验证；运行时生成器由后续任务实现。
- 测试与 fixture 可使用确定性合法 ULID；生产生成必须使用密码学安全随机源。

## API 直接字符串映射

task_id、article_id、article_version_id、task_article_id、job_id、plugin_id、tokenId、session_id 及其他目标实体 ID 均直接映射对应实体的 ULID 主键文本：

- JSON 类型仍为 string。
- API 与 DB 之间不进行 BINARY(16)、Base64 或数字转换。
- 输入引用验证 canonical ULID。
- 输出保持相同 26 位大写字符串。
- tokenId 是 APIToken 实体 ID，不是 token secret。
- session_id 是 Session 实体 ID，不是 session secret。
- article_key、content_hash、checksum、idempotency_key 不是实体主键，不得改成 ULID。

## Legacy ID 不直接转换

旧 8 字符 UUID 截断值、旧 BIGINT ID、64 位十六进制任务标识均为 legacy 标识。DEV-004 B3 不强制转换这些值；未来专用 legacy 迁移程序必须分配新 ULID，并保存旧 ID 到新 ID 的映射。

## 安全、索引和排序影响

- canonical ULID 使用受限字符集，可安全用于 URL path、JSON string 与 ascii_bin 索引。
- CHAR(26) ascii_bin 不区分大小写问题，索引固定长度，不使用前缀索引。
- ULID 时间前缀可以粗排序，但不能替代 UTC 业务时间字段。
- 所有 ULID FK 与父列类型、长度、charset、collation 必须一致，避免 MySQL errno 3780。

## 不采用方案

- UUID 文本：长度更长且无单调排序优势。
- BINARY(16)：需要 API/DB 双向编码转换。
- 多表 AUTO_INCREMENT：泄露规模，且跨服务引用不可移植。
- 数据库默认表达式或触发器生成：使 ID 生成离开 Go 权威写入边界。
