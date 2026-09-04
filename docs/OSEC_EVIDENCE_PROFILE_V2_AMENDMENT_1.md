# OSEC Evidence Profile V2 Amendment 1

文档状态：Draft / IMPLEMENTED_WAITING_REVIEW

规范文档机器标识：`OSEC-EVIDENCE-PROFILE-V2-AMENDMENT-1`

本文件是 `OSEC-EVIDENCE-PROFILE-V2` 的增量规范。Manifest 和 Seal 中的 `profile` 字段值仍为 `OSEC-EVIDENCE-PROFILE-V2`。Amendment 机器标识只标识本规范文档，不作为第二个 profile 字段值，也不新增 `profile_revision` 序列化字段。

基础规范与增量冲突时，仅对新增 V2 组件采用本 Amendment 规则；V1 组件及既有产物继续按基础规范解释。

## 1. 适用范围

- 本文件只定义 Evidence Profile V2 的 V2 组件增量。
- 不修改已封板的 `OSEC-EVIDENCE-PROFILE-V2` 基础规范。
- 不修改 125-case fixture、Legacy Record、V1 聚合或既有候选 V1 实现。
- V1 组件继续有效，V2 组件用于新的 Canonical、Manifest、Seal 实施。

## 2. MISMATCH 事实记录

分类：`spec_ambiguity`

- V1 候选 commit：`fffb01db5e9efdcbb4e526107fcfeaf1b5a4eaae`
- Legacy Record commit：`a0bd91f03aef881713b4d78b3eef895c77ea005f`
- `p-004`：path=`/ports/https/0`，raw lexeme=`443.0`，Legacy digest=`4ed0c899258ba53fe64eaf92b2b243281f9dbd0cfe8fae4b5c6ba76bcc38fd50`，V1 结果=`canonical_non_integer_number`
- `ver-003`：path=`/value`，raw lexeme=`1.0`，Legacy digest=`5ff23879522951099e3d6d44f8f74884905f23e29ebb64b17ed63efea5066806`，V1 结果=`canonical_non_integer_number`

说明：

- 案例对象是证据容器，必须能够表达被测试配置中的非法类型。
- Canonical 层禁止所有非整数会使此类证据无法被哈希。
- 该问题不是实现错误、向量错误或 Legacy 异常。
- 未授权 `intentional_break`。
- 不修改 125-case、Legacy Record 或冻结聚合。

## 3. 版本映射

保持并冻结：

- OSEC-EVIDENCE-PROFILE-V2
- OSEC-STRICT-JSON-DECODE-V1
- OSEC-EVIDENCE-LIMITS-V1
- OSEC-CANONICAL-JSON-V1
- OSEC-CANONICAL-CASE-V1
- OSEC-CASE-AGGREGATE-V1
- OSEC-CASE-CATEGORY-AGGREGATE-V1
- OSEC-CASE-MANIFEST-V1
- OSEC-SEAL-RECORD-V1
- OSEC-LEGACY-DIGEST-RECORD-V1
- OSEC-CASE-MERKLE-DRAFT-0

新增：

- OSEC-EVIDENCE-PROFILE-V2-AMENDMENT-1
- OSEC-EVIDENCE-LIMITS-V2
- OSEC-CANONICAL-JSON-V2
- OSEC-CANONICAL-CASE-V2
- OSEC-CASE-MANIFEST-V2
- OSEC-SEAL-RECORD-V2

状态：

- CanonicalJSON/Case/Limits V1 继续有效。
- Manifest V1 与 Seal V1 保留为历史规范。
- 本项目未生成过 Manifest V1 或 Seal V1 实例。
- Manifest V1/Seal V1 在本项目中标记为 `SUPERSEDED_BEFORE_IMPLEMENTATION`。
- 后续实施目标为 Manifest V2 与 Seal V2。
- Aggregate 与 Category Aggregate 保持 V1，不升级。

## 4. StrictDecode 与类型化 AST

- 不新增 `OSEC-STRICT-JSON-DECODE-V2`。
- StrictDecode V1 的 JSON 语法、UTF-8、BOM、代理、duplicate、尾随数据规则不变。
- typed AST 继续包含 `IntegerNumber` 与 `NonIntegerNumber(raw_lexeme)`。
- `strict_decode_v2` 只是 StrictDecode V1 + EvidenceLimits V2 的 API 预设，不是新的 StrictDecode 算法版本。
- Manifest V2 仍声明 `strict_decode_version=OSEC-STRICT-JSON-DECODE-V1`。

## 5. EvidenceLimits V2

固定默认值：

- file_size=16,777,216 raw bytes
- nesting_depth=128
- number_digits=4096
- array_length=10,000
- object_members=1,000
- string_length=1,048,576 decoded UTF-8 bytes
- case_count=10,000

`number_digits` 统计：

- coefficient 整数部分全部数字
- coefficient 小数部分全部数字
- exponent 全部数字

不统计：

- 数字开头负号
- 小数点
- e/E
- exponent 正负号

示例：

- `1.0` = 2 digits
- `-0.0` = 2 digits
- `1e5` = 2 digits
- `-1.25e+3` = 4 digits
- 4096 接受，4097 拒绝

错误码：

- 新增 `evidence_limit_number_digits`
- V1 的 `evidence_limit_integer_digits` 保持冻结，仅用于 V1
- V2 整数与非整数统一使用 `number_digits`

错误优先级：

- invalid JSON grammar 先于 number_digits
- trailing data 按基础规范
- lone surrogate 按基础规范
- duplicate key 先于 AST limits
- 语法合法且无 duplicate 后才执行 number_digits
- direct API 合法 lexeme 超限返回 `evidence_limit_number_digits`

## 6. CanonicalJSON V2

合法 NonIntegerNumber raw lexeme 语法：

```text
-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?
```

并且必须包含小数点或 e/E。

规范化行为：

- 输出 raw lexeme 原始 ASCII bytes
- 不执行 float/Decimal 转换
- 不执行 IEEE-754
- 不做数值运算
- 不删除尾零
- 不改变 e/E 大小写
- 不删除指数正号
- 不扩展或压缩指数
- 不归一化负零
- 不添加空白
- 不添加 BOM 或末尾 LF
- 不执行结果字符串 replace

固定映射：

- `1.0` → `1.0`
- `443.0` → `443.0`
- `1.00` → `1.00`
- `1e5` → `1e5`
- `1E+5` → `1E+5`
- `-0.0` → `-0.0`
- `0.10` → `0.10`

`1.0`、`1.00`、`1e0` 是不同证据字节；数字词法差异属于证据内容差异。IntegerNumber 规则不变，`-0` 仍规范化为 `0`。其他字符串、key 排序、Unicode 和容器规则全部继承 CanonicalJSON V1。

## 7. API 直接构造规则与错误码

V2 允许显式 Python `NonIntegerNumber(raw_lexeme)` 或 Go 等价 Value/NonInteger 表示进入 CanonicalJSON V2，但必须：

1. 验证 raw 值为字符串或合法字节表示
2. 验证完整 JSON 数字语法
3. 验证确实包含 `.` 或 `e/E`
4. 验证 number_digits 限制
5. 原样输出 lexeme

新增错误码：

- `canonical_invalid_number_lexeme`
- `evidence_limit_number_digits`

适用 `canonical_invalid_number_lexeme`：

- 非法 JSON 数字语法
- wrapper 内容实际是整数 lexeme
- 含空白
- 含前导加号
- 含前导零
- 截断指数
- NaN/Infinity
- 非 ASCII 数字字符

错误边界：

- 合法但超 4096 digits：`evidence_limit_number_digits`
- Python float/Decimal、Go float32/float64：`canonical_invalid_value_type`
- CanonicalJSON V1 遇到 NonIntegerNumber：`canonical_non_integer_number`

V2 有效错误码集合：

- 基础规范 40 码全部保留
- 新增 `evidence_limit_number_digits`
- 新增 `canonical_invalid_number_lexeme`
- V2 有效集合总数为 42
- 不删除或重新定义任何 V1 机器码

## 8. CanonicalCase V2

- root 必须 object
- 必须存在 id
- id 正则保持 `^[a-z][a-z0-9-]{0,63}$`
- 使用 CanonicalJSON V2 生成 canonical bytes
- digest：`SHA256(CanonicalJSONV2(case_object))`
- id 继续参与 digest
- 其他 Case 规则继承 V1

预演兼容结果（非正式门禁）：

- candidate=125
- legacy=125
- missing=0
- extra=0
- duplicate=0
- mismatch=0
- `p-004` 与 `ver-003` digest 等于 Legacy
- 三个 Aggregate V1 保持原值

冻结文本值：

- ALL125=`75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b`
- BASE104=`bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8`
- AMENDMENT21=`dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850`

预演不得写成正式 A0.3b MATCH。

## 9. 建议公开 API

Python：

- `DEFAULT_LIMITS_V2`
- `strict_decode_v2`
- `canonical_json_v2`
- `canonical_case_v2`

Go：

- `DefaultEvidenceLimitsV2`
- `StrictDecodeV2`
- `CanonicalJSONV2`
- `CanonicalCaseV2`

要求：

- V1 API 及默认值不变
- 复用已有 typed AST
- V2 API 命名明确
- 不通过环境变量改变 limits
- direct wrapper 执行防御性验证

## 10. Manifest V2

信封：

- `manifest_v2`
- `manifest_hash_v2`

hash：

```text
SHA256(
  "OSEC-CASE-MANIFEST-HASH-V2\0"
  || CanonicalJSONV2(manifest_v2)
)
```

版本字段：

- manifest_version=OSEC-CASE-MANIFEST-V2
- profile=OSEC-EVIDENCE-PROFILE-V2
- strict_decode_version=OSEC-STRICT-JSON-DECODE-V1
- evidence_limits_version=OSEC-EVIDENCE-LIMITS-V2
- canonical_json_version=OSEC-CANONICAL-JSON-V2
- canonical_case_version=OSEC-CANONICAL-CASE-V2
- aggregate_algorithm=OSEC-CASE-AGGREGATE-V1
- category_aggregate_algorithm=OSEC-CASE-CATEGORY-AGGREGATE-V1
- digest_algorithm=SHA-256

数据字段与 Manifest V1 语义保持：dataset、case_count、cohorts、category_names、whole_set_aggregate_v1、category_aggregates、case_digests。排序、cohort、category、unknown field、复算、自包含及能力边界继承 Manifest V1。

禁止包含：

- profile_revision
- fixture 文件自身 SHA
- Legacy Record 引用
- manifest_hash_v1

## 11. Seal Record V2

信封：

- `seal_record_v2`
- `seal_record_hash_v2`

hash：

```text
SHA256(
  "OSEC-SEAL-RECORD-HASH-V2\0"
  || CanonicalJSONV2(seal_record_v2)
)
```

内部必填字段仍为 17 个，仅进行版本一致性替换：

1. seal_record_version
2. profile
3. dataset
4. manifest_hash_v2
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

固定：

- seal_record_version=OSEC-SEAL-RECORD-V2
- profile=OSEC-EVIDENCE-PROFILE-V2
- review_result=PASS 才是有效 Seal
- Git 绑定、外部报告、S1 语义继承 Seal V1
- Manifest 字段必须是 manifest_hash_v2
- 禁止 manifest_hash_v1
- Seal V1 不得锚定 Manifest V2

## 12. V2 黄金向量要求

未来新增：

```text
tests/fixtures/outbound_security_canonical_v2_vectors.json
```

不得修改 A0.2 fixture。

V2 符合性测试必须：

- 消费原 A0.2 全部 25 条 V1 valid
- 独立消费 V2 增量向量
- 不把 V1 reject expected 改写为 V2 expected
- V1 与 V2 测试并存

V2 valid inventory 至少包括：

- number_1_0
- number_443_0
- number_1_00
- number_1e5
- number_1E_plus_5
- number_negative_zero_fraction
- number_zero_fraction
- number_0_10
- number_1e_minus_5
- number_negative_1_25e_plus_3
- number_digits_4096
- canonical_case_p004_shape
- canonical_case_ver003_shape

V2 reject/resource 至少包括：

- number_digits_4097
- direct_wrapper_integer_lexeme
- direct_wrapper_leading_plus
- direct_wrapper_leading_zero
- direct_wrapper_truncated_exponent
- direct_wrapper_nan
- direct_wrapper_infinity
- direct_wrapper_whitespace
- direct_wrapper_non_ascii_digit

JSON 无法表达的 direct wrapper 负向放语言本地测试，不伪造 fixture JSON。Expected 必须独立人工构造，不得由未来候选实现录制。

## 13. A0.3b 重新门禁

正式 V2 门禁必须：

- 使用封板 V2 候选
- 使用同一 125-case fixture
- 使用同一 Legacy Record
- 125/125 digest 完全相等
- 三个 Aggregate V1 完全相等
- Python/Go 均通过
- 不接受 123+2 例外
- 不使用混合 canonical 来源
- 不修改历史 expected

V1 MISMATCH 必须永久保留；V2 成功时新增 V2 MATCH 字段，不得覆盖历史。

## 14. V1 资产保护

以下内容永久保留且不得修改：

- 125-case fixture
- Legacy Record
- V1 三个聚合值
- CanonicalJSON/Case/Limits V1
- E/A1 候选 V1 提交
- Manifest V1 / Seal V1 历史定义

V2 只新增组件，不重写 V1 语义。

## 15. 迁移与停止条件

以下情况必须 STOP：

- V2 预演或正式门禁出现 digest mismatch
- Python 与 Go 结果不一致
- 需要修改 V1 资产
- 需要自动重锚
- 需要新增依赖或生产接线
- 需要在 Manifest/S1/Seal 完成前声明 MATCH
- Git 现场发生变化

迁移顺序：V2 增量规范 → V2 黄金向量 → Python/Go V2 候选 → A0.3b V2 门禁 → Manifest V2 → S1 → Seal Record V2 → 返回生产 loader 任务。
