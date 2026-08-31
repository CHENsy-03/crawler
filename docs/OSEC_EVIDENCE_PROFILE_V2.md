# OSEC Evidence Profile V2

文档状态：A0.1 NORMATIVE DRAFT / IMPLEMENTED_WAITING_REVIEW

- Profile V2 已完成研究设计冻结，但尚未通过项目内 A0 审核。
- 当前没有任何 Python/Go 符合性实现。
- Manifest、Legacy Record、Seal Record 尚未创建。
- 不代表 production loader 或部署已完成。
- S0 仅为旧行为来源锚点：`e6bdf4c863903fa7e2fdafd004fc94d0fbb766a3`。
- 不得声称新 CanonicalCase 已与历史 125 cases 兼容；该结论必须等待 A0.3b。

身份与命名：

本规范的人类可读名称为 `OSEC Evidence Profile V2`；唯一规范机器常量为 `OSEC-EVIDENCE-PROFILE-V2`。二者表示同一个 Evidence Profile。人类可读名称仅用于标题和说明文字；Manifest、Seal及所有序列化、哈希输入和机器比较场景必须使用规范机器常量。

- 人类可读名称：`OSEC Evidence Profile V2`
- 唯一规范机器常量：`OSEC-EVIDENCE-PROFILE-V2`
- Manifest V1 的 profile 字段必须精确等于：`OSEC-EVIDENCE-PROFILE-V2`
- Seal Record V1 的 profile 字段必须精确等于：`OSEC-EVIDENCE-PROFILE-V2`
- 验证器必须拒绝空格形式、大小写变体、下划线变体或其他版本作为机器字段值。

## 1. 版本映射

组件与版本：

- 人类可读名称：`OSEC Evidence Profile V2`
- 唯一规范机器常量：`OSEC-EVIDENCE-PROFILE-V2`
- `OSEC-EVIDENCE-PROFILE-V2`：Profile 机器常量，当前 A0.1 NORMATIVE DRAFT
- OSEC-STRICT-JSON-DECODE-V1：组件版本，Draft 待 A0.2 黄金向量
- OSEC-EVIDENCE-LIMITS-V1：组件版本，Draft 待 A0.2 黄金向量
- OSEC-CANONICAL-JSON-V1：组件版本，Draft 待 A0.2 黄金向量
- OSEC-CANONICAL-CASE-V1：组件版本，Draft 待 A0.2 黄金向量
- OSEC-CASE-AGGREGATE-V1：Frozen；成功输入字节格式与 S0 完全一致
- OSEC-CASE-CATEGORY-AGGREGATE-V1：组件版本，Draft 待 A0.2 黄金向量
- OSEC-CASE-MANIFEST-V1：组件版本，Draft，未创建文件
- OSEC-LEGACY-DIGEST-RECORD-V1：组件版本，Draft，未创建文件
- OSEC-SEAL-RECORD-V1：组件版本，Draft，未创建文件
- OSEC-CASE-MERKLE-DRAFT-0：Draft 组件，仅观察，不实现

区分：

- Profile 版本：OSEC Evidence Profile V2
- 组件版本：上述各 V1/DRAFT 组件
- 已冻结算法：OSEC-CASE-AGGREGATE-V1
- Draft 组件：其余全部
- 实现状态：无 Python/Go 符合性实现
- 符合性状态：未声明任何符合性等级

## 2. 分层模型

规范化链：

```text
raw bytes
→ Strict JSON Decode
→ typed AST
→ Evidence Limits
→ Canonical JSON
→ Canonical Case
→ case digest
→ whole/category aggregate
→ Manifest
→ S1
→ external Seal Record
```

边界：

- Fixture schema/invariant 属数据集合同层。
- policy_id 不属于 CanonicalCase。
- CanonicalJSON 不要求对象具有 id。
- CanonicalCase 才要求 case 根对象及 case_id。
- Manifest 和 Seal 直接使用 CanonicalJSON，不能硬塞无业务意义的 id。

## 3. StrictFixtureDecode-V1（OSEC-STRICT-JSON-DECODE-V1）

- 原始输入为 bytes。
- BOM 在文件起始位置拒绝；字符串内部 U+FEFF 允许。
- JSON 解析前严格验证 UTF-8，禁止 U+FFFD 替换。
- 恰好一个 JSON 值；合法第一值后的非空白内容为 `strict_decode_trailing_data`。
- JSON 语法错误为 `strict_decode_invalid_json`。
- NaN、Infinity、-Infinity 均为 invalid_json。
- 重复 key 按解码后的 Unicode key 比较。
- `{"a":1,"\u0061":2}` 必须判重复 key。
- 只有完整 JSON 语法成立后，才能返回 duplicate_key。
- malformed JSON 中即使表面存在重复 key，也必须返回 invalid_json。
- 孤立代理、高高代理、低代理单出、错误配对全部拒绝。
- 合法原始 U+FFFD 允许。
- Go 使用“标准库 Token 解析 + 窄字符串转义/代理预检”，不实现第二套完整 JSON parser。
- 窄预检只拒绝，不负责接受 JSON；标准库解析器是 JSON 语法唯一权威。
- Python 数字入口使用 IntegerLexeme/NonIntegerNumber，不能直接 `parse_int=int`。
- Go 使用 UseNumber 保留原始 lexeme。
- 无 `.`、`e`、`E` 的合法 JSON 数字进入任意精度整数。
- `-0` 规范为整数 0。
- 含小数点或指数的合法数字保留为 NonIntegerNumber，交给 canonical 层拒绝。
- 首错规则采用阶段顺序：文件大小前置检查 → 严格 UTF-8 → 完整 JSON 语法/尾随 → duplicate key → typed-AST 构建时的 evidence limits → canonical。不得重新启用“所有 evidence limits 一律先于 invalid_json”。

## 4. EvidenceLimits-V1（OSEC-EVIDENCE-LIMITS-V1）

- 文件最大 16 MiB，即 16,777,216 bytes。
- 嵌套深度最大 128。
- 整数字面量最多 4096 个十进制数字；负号不计入。
- 单数组最多 10,000 个直接元素。
- 单对象最多 1,000 个原始成员；重复成员在折叠前计数。
- 单字符串解码后 UTF-8 长度最大 1 MiB，即 1,048,576 bytes；对象 key 同样适用。
- case 总数最大 10,000。

说明：

- 限制不进入 canonical 字节。
- 限制只控制资源和符合性输入域。
- 文件大小是原始字节级前置保护。
- 其余限制在 token/typed-AST 构建的明确执行点检查。
- 不依赖 Python `int_max_str_digits`。
- 根容器深度计为 1；每进入一层 object/array，深度 +1；scalar 不增加容器深度。
- 每层首错返回，不能输出错误输入的原始敏感内容。

## 5. CanonicalJSON-V1（OSEC-CANONICAL-JSON-V1）

类型化 AST 仅允许：

- null
- bool
- arbitrary-precision integer
- string
- array
- object

NonIntegerNumber 必须返回：`canonical_non_integer_number`。

禁止 float、bytes、循环引用和语言专属对象直接进入 API。

对象 key：

- 可以是任意合法 Unicode 字符串。
- 不进行 ASCII 正则限制。
- 不进行 NFC/NFD 归一化。
- 递归按 Unicode scalar value 顺序排序。
- 对合法 UTF-8，该顺序与 UTF-8 字节序一致。

字符串唯一编码规则：

- `"` → `\"`
- `\` → `\\`
- U+0008/U+0009/U+000A/U+000C/U+000D 使用 `\b/\t/\n/\f/\r`
- 其他 U+0000–U+001F 使用小写 `\u00xx`
- `/` 原样输出
- U+0020 及以上原始 UTF-8 输出
- `<`、`>`、`&`、U+007F、U+2028、U+2029 不转义
- 字面反斜杠-u 文本必须作为普通字符串处理，禁止事后字符串替换
- 无额外空白、无 BOM、无结尾换行
- 不进行 Unicode normalization

Python 行为：

- `ensure_ascii=False`
- `sort_keys=True`
- `separators=(",", ":")`
- `allow_nan=False`
- `skipkeys=False`
- 要求值域前置验证

Go 行为：

- 使用专用递归 canonical encoder。
- 不依赖 `encoding/json` 的 HTML escaping 行为。

## 6. CanonicalCase-V1（OSEC-CANONICAL-CASE-V1）

- 根必须为 object，否则 `canonical_root_not_object`。
- 必须有 `id`，否则 `canonical_missing_id`。
- case_id 正则：`^[a-z][a-z0-9-]{0,63}$`。
- 非法 ID：`canonical_invalid_id`。
- `d_i = SHA256(CanonicalJSON(case_object))`。
- id 本身参与 CanonicalJSON 和 d_i。
- policy_id 规则属于 outbound 数据集合同，不属于该通用证据层。

## 7. Aggregate-V1（OSEC-CASE-AGGREGATE-V1）

本节的成功输入字节格式从 S0 已封板测试源码逐字核实，不凭记忆重写。

Magic：

```text
OSEC-CASE-AGGREGATE-V1\0
```

布局：

```text
MAGIC
|| U32BE(count)
|| 对按 case ID UTF-8 字节序升序的每条记录：
   U32BE(id_utf8_length)
   || id_utf8
   || 32-byte raw SHA-256 case digest
```

- U32BE 为 4-byte unsigned big-endian。
- digest 恰为 32 bytes。
- 按 ID UTF-8 字节序排序。
- 输入物理顺序不影响结果。
- 集合非空；空集合返回 `aggregate_empty_set`。
- ID 唯一；重复返回 `aggregate_duplicate_id`。
- digest 长度不是 32 bytes 返回 `aggregate_invalid_digest_length`。
- count 或 id length 超过 U32 上限返回 `aggregate_count_overflow` / `aggregate_length_overflow`。
- 未知算法返回 `aggregate_unknown_algorithm`。
- 摘要算法固定 SHA-256；更换摘要必须升级算法版本。
- 成功输入域字节格式与 S0 完全一致。

冻结值（S0 legacy 行为证据）：

- BASE104_V1 = `bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8`
- NEW21_V1 = `dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850`
- ALL125_V1 = `75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b`

这些值属于 S0 的 legacy 行为证据。不得提前声称它们已由新 CanonicalJSON 实现复现。

## 8. Category Aggregate V1（OSEC-CASE-CATEGORY-AGGREGATE-V1）

Magic：

```text
OSEC-CASE-CATEGORY-AGGREGATE-V1\0
```

布局：

```text
MAGIC
|| U32BE(category_name_utf8_length)
|| category_name_utf8
|| U32BE(count)
|| 按 case ID UTF-8 字节序升序的排序记录（与 Aggregate-V1 相同）
```

约束：

- category name 正则：`^[a-z][a-z0-9_]{0,63}$`。
- 非空集合；ID 唯一；digest 32 bytes。
- U32 溢出拒绝。
- 分类名域绑定不得修改原 Aggregate-V1。

## 9. Manifest V1（OSEC-CASE-MANIFEST-V1）

未来独立文件路径：

```text
tests/fixtures/outbound_security_config_manifest.json
```

信封：

- `manifest_v1`
- `manifest_hash_v1`

哈希：

```text
SHA256(
  "OSEC-CASE-MANIFEST-HASH-V1\0"
  || CanonicalJSON(manifest_v1)
)
```

- hash 不包含信封中的自身字段。

Manifest 字段：

- manifest_version
- profile
- strict_decode_version
- evidence_limits_version
- canonical_json_version
- canonical_case_version
- aggregate_algorithm
- category_aggregate_algorithm
- digest_algorithm
- dataset
- case_count
- cohorts
- category_names
- whole_set_aggregate_v1
- category_aggregates
- case_digests

约束：

- dataset：`^[a-z][a-z0-9_-]{0,63}$`
- Manifest V1 的 profile 字段必须精确等于：`OSEC-EVIDENCE-PROFILE-V2`
- category_names UTF-8 升序、非空、唯一
- case_digests 按 id UTF-8 升序
- 每项包含 id/category/64 位小写 SHA-256 hex
- 每个案例恰属一个 category
- category key 集合精确等于 category_names
- 分类计数总和等于 case_count
- whole/category/cohort 聚合均能重算
- cohorts 按 name UTF-8 升序
- cohort 非空
- cohort ID 跨 cohort 互斥
- cohort 并集等于全集
- cohort name：`^[a-z][a-z0-9_-]{0,63}$`
- 禁止 fixture 文件自身 SHA 进入 Manifest
- Manifest 字段不得进入 case aggregate
- unknown field fail-closed

兼容桥：

- `base104.aggregate_v1 == BASE104_V1`
- `amendment21.aggregate_v1 == NEW21_V1`
- base104.case_ids 与 fixture.baseline_case_ids 集合相等
- fixture 旧字段保留为 V1 兼容镜像
- 上述跨文件桥由共享合同测试负责，不新增 OSEC 运行时错误码

能力边界：

> Manifest 可独立验证其内部摘要集合和聚合关系的一致性；仅凭 Manifest 不能证明 case digest 来自真实 fixture 案例内容。

## 10. Legacy Record 与 S0/S1

未来路径：

```text
tests/fixtures/outbound_security_config_legacy_digests.json
```

双锚点：

- S0 = LEGACY_SOURCE_COMMIT `e6bdf4c863903fa7e2fdafd004fc94d0fbb766a3`
- S1 = EVIDENCE_SEAL_COMMIT，尚未创建

流程：

- A0.3a 在后续提交 L 中录制 S0 旧 Python 行为。
- provenance 标记为 `recorded-from-legacy`。
- 记录 python_version、S0 commit/tree、fixture path/blob、125 个 case digest 和三个聚合。
- legacy 记录不可伪装成 independently-constructed golden vector。
- legacy 记录不进入 case aggregate。
- 不参与 Manifest hash。
- 不被 Seal Record 当作权威锚点。
- 创建后不可随新规范更新。

A0.3b：

- 候选实现与 legacy 125-case 逐案例比较。
- MATCH 才能继续 Manifest。
- MISMATCH 必须 STOP。
- 人工分类仅允许：implementation_bug、vector_bug、spec_ambiguity、legacy_anomaly、intentional_break。
- 只有明确授权的 intentional_break 才允许重锚。
- 不得自动启用新的 canonical 值。

## 11. Seal Record V1（OSEC-SEAL-RECORD-V1）

Seal 位于仓库外的只读审计报告中，不得写入被证明的 S1 提交。

信封：

- `seal_record_v1`
- `seal_record_hash_v1`

哈希：

```text
SHA256(
  "OSEC-SEAL-RECORD-HASH-V1\0"
  || CanonicalJSON(seal_record_v1)
)
```

冻结 17 个必填字段：

1. seal_record_version
2. profile
3. dataset
4. manifest_hash_v1
5. whole_set_aggregate_v1
6. repo_id
7. git_object_format
8. commit_oid
9. tree_oid
10. fixture_path
11. fixture_blob_oid
12. manifest_path
13. manifest_blob_oid
14. auditor
15. audited_at_utc
16. audit_program
17. review_result

要求：

- review_result 必须精确为 PASS 才构成有效 Seal。
- FAIL/BLOCKED 只能是普通审计报告。
- whole_set_aggregate_v1 是 Manifest 值的冗余回显，不是第二权威。
- BASE104/NEW21 只能放非规范附录并标记 `derived_from_sealed_manifest`。
- branch 等可变信息只能放非规范上下文，不进入上述 17 字段。
- repo_id 不能使用可能含凭据的 remote URL。
- fixture/manifest 路径必须在 S1 tree 中解析到对应 blob。
- Seal Record V1 的 profile 字段必须精确等于：`OSEC-EVIDENCE-PROFILE-V2`
- Verifier 必须验证 commit 存在、tree 匹配、路径 blob 匹配、Manifest hash 与 whole aggregate 匹配。
- 未来签名直接签规范 Seal 字节；当前不引入签名或密钥管理。

## 12. Merkle

组件名：

```text
OSEC-CASE-MERKLE-DRAFT-0
```

- 不得称 V1，不实现。
- 启用前必须另行冻结：叶排序、叶/内部节点域分离、奇数节点规则、单叶 root、leaf count 根绑定、proof index/方向和兄弟顺序、空集行为、双端黄金向量。
- 观察 2–3 轮 Manifest 审计后再决定。

## 13. 全前缀错误码

Strict decode：

- strict_decode_invalid_json
- strict_decode_invalid_utf8
- strict_decode_bom
- strict_decode_duplicate_key
- strict_decode_lone_surrogate
- strict_decode_trailing_data

Evidence limits：

- evidence_limit_file_size
- evidence_limit_nesting_depth
- evidence_limit_integer_digits
- evidence_limit_array_length
- evidence_limit_object_members
- evidence_limit_string_length
- evidence_limit_case_count

Canonical：

- canonical_invalid_value_type
- canonical_non_integer_number
- canonical_invalid_unicode
- canonical_root_not_object
- canonical_missing_id
- canonical_invalid_id

Aggregate：

- aggregate_empty_set
- aggregate_duplicate_id
- aggregate_invalid_digest_length
- aggregate_unknown_algorithm
- aggregate_count_overflow
- aggregate_length_overflow

Manifest：

- manifest_invalid_structure
- manifest_unknown_field
- manifest_count_mismatch
- manifest_case_digest_mismatch
- manifest_category_mismatch
- manifest_aggregate_mismatch
- manifest_invalid_dataset
- manifest_invalid_category
- manifest_duplicate_category
- manifest_invalid_cohort
- manifest_duplicate_cohort
- manifest_cohort_mismatch

Seal：

- seal_record_invalid_structure
- seal_record_hash_mismatch
- seal_record_git_binding_failed

错误文案不要求双端一致，但必须不泄密、清晰且与机器码一致。

## 14. 黄金向量要求

A0.1 只定义格式，不创建向量文件。

未来路径建议：

```text
tests/fixtures/outbound_security_aggregate_vectors.json
```

有效向量字段：

- name
- input_json_utf8_hex
- expected_canonical_utf8_hex
- expected_case_sha256

拒绝向量字段：

- name
- input_json_utf8_hex 或确定性 generator recipe
- expected_stage
- expected_error

必须覆盖：

- `<>&`
- U+2028、U+2029
- 字面 `\u2028` 文本
- CJK
- 控制字符
- 嵌套乱序 key
- 非 ASCII Unicode key 作为合法输入
- null/bool/int/string/array/object 判型
- 超 int64 大整数
- `-0` 与 `0` 同 canonical
- `\/` 规范为 `/`
- U+007F/C1
- 格式、缩进、CRLF 不同但同 canonical
- duplicate decoded key
- BOM、非法 UTF-8、所有代理错误组合
- trailing data
- NaN/Infinity
- 合法非整数数字
- 非法 JSON 数字语法
- case_id、dataset、category 边界
- 所有 evidence limits

不得保留已废弃的“object key ASCII/64 字节限制”拒绝向量。

大于 16 MiB 的向量不得内嵌巨大 hex，必须使用确定性 recipe：

- generator
- unit_hex
- count
- expected_input_sha256
- expected_stage
- expected_error

黄金 expected：

- 不得由 Python 或 Go 候选生产实现录制。
- 人工构造 hex。
- 使用两个通用 SHA-256 工具核验。
- 可使用一次性独立参考实现交叉检查。
- 与 recorded-from-legacy 证据严格分离。

## 15. 三权威治理与符合性等级

三权威：

- fixture cases = 内容权威
- Manifest = V2 证据权威
- fixture 旧 aggregate 字段 = V1 兼容镜像

生成规则：

- 确定性工具只从 cases 派生 Manifest 与兼容字段。
- 默认测试只能验证，不能自动改写。
- 写入必须由显式更新任务触发。
- 另一语言独立复核。
- Manifest 不反向生成案例内容。

符合性等级：

- Decode
- Canonical
- Aggregate
- Manifest
- Seal Verifier
- Full OSEC Evidence Profile V2

Python 与 Go 必须分别声明等级，不能用一端通过替代另一端。

## 16. 实施门禁图

```text
A0.1 文字规范
→ A0.2 独立黄金向量
→ A0.3a 录制 S0 legacy 行为
→ E/A1 候选双端实现
→ A0.3b 125-case兼容门禁
→ B Manifest
→ S1 EVIDENCE_SEAL_COMMIT
→ D 外部 Seal Record
→ Merkle 继续观察
→ 返回 TASK-022E-C production loader
```

候选实现通过 A0.3b 前不得接入生产。
