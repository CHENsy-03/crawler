# TASK-022E Production Outbound Security Configuration Contract

**Status：** CONTRACT_FIX_COMPLETED / WAITING_RE_REVIEW / UNCOMMITTED（TASK-022E-B，生产 loader 未实现）
**config file（仅冻结路径，不创建）：** `config/outbound_security.json`
**Schema：** `config/outbound_security.schema.json`
**Shared fixture：** `tests/fixtures/outbound_security_config_contract.json`

## 1. V1 配置结构

顶层只允许 `config_version` 与 `policies`；policy 只允许 `policy_id`、`allowed_domains`、`allowed_schemes`、`allowed_ports`。

```json
{
  "config_version": "1.0",
  "policies": [
    {
      "policy_id": "site-policy-id",
      "allowed_domains": ["example.com"],
      "allowed_schemes": ["https"],
      "allowed_ports": {"https": [443]}
    }
  ]
}
```

- `config_version` 必须为字符串 `"1.0"`；未知/缺失/null/数字/bool/空串拒绝，不自动降级。
- `policy_id` 1–64 字符，小写 ASCII 字母开头，仅 `a-z0-9_-`。
- `allowed_domains` 仅规范化小写 ASCII IDNA A-label，且必须至少包含两个 DNS label（至少一个点）；无 root dot、scheme、userinfo、path/query/fragment、port、通配符、IP literal；单标签 `localhost`、`example` 一律 `config_invalid_hostname`。
- `allowed_schemes` 仅允许 `["https"]` 或 `["http","https"]`。
- `allowed_ports` 为 scheme→整数端口列表，端口 1–65535，列表非空、唯一、升序；key 必须与 `allowed_schemes` 精确一致。
- 禁止字段：`allowed_subdomain_roots`、`redirect_allowed_domains`、`redirect_allowed_subdomain_roots`、`allow_http`、`allow_controlled_subdomains`、`proxy`、私网开关、TLS disable、budget/profile override、内联 site override、凭据、完整 URL。

## 2. Schema 边界

Schema 只表达静态结构约束（additionalProperties=false、required、const "1.0"、policy_id pattern、hostname ASCII pattern、scheme 两种 canonical 组合、port 整数范围）。

Schema 无法单独验证：

- duplicate JSON key（解析器相关）
- IDNA 语义与 Unicode 规范化
- IP literal（hostname pattern 允许纯数字 label）
- canonical 重复（大小写/root dot 归一后重复）
- site policy 引用
- site URL 交叉校验
- allowed_schemes 与 allowed_ports key 精确相等

以上必须由后续生产 loader 执行。不得新增 JSON Schema 依赖；后续生产校验不得依赖第三方库，除非另行批准。

## 3. 稳定 reason code

`config_missing`、`config_invalid_json`、`config_invalid_top_level`、`config_unsupported_version`、`config_unknown_field`、`config_missing_field`、`config_invalid_type`、`config_duplicate`、`config_invalid_policy_id`、`config_invalid_hostname`、`config_forbidden_ip_literal`、`config_invalid_scheme`、`config_invalid_port`、`config_invalid_policy_reference`、`config_site_host_not_covered`、`config_conflict`、`config_unreadable`、`config_limit_exceeded`。

已删除不再适用的 `config_invalid_redirect_subset`。18 个 reason 全部具有可回放 fixture case。新增：
- `config_unreadable`：固定路径目录项存在，但无法安全解析为可读配置源（权限拒绝、open/read 失败、目录/非普通文件、broken symlink、读取中 I/O 错误）；不得用于路径不存在、空文件、UTF-8/JSON/Schema 错误、大小/深度超限。
- `config_limit_exceeded`：原始配置超过 1,048,576 bytes，或完整、语法合法 JSON 容器嵌套深度超过 32；不得用于权限/读取错误、非法 UTF-8、malformed JSON、普通字段/数组数量错误。

日志不得包含原始配置、完整 URL、query、Cookie、Authorization 或凭据。

## 4. 决策摘要（E-01..E-16）

- E-01：独立文件 `config/outbound_security.json`，本阶段只冻结路径。
- E-02：policy registry + 站点显式 `outbound_policy_id`；禁止 site 内联安全 override；无默认放行 policy。
- E-03：hostname 只能规范化小写 ASCII IDNA A-label，且至少两个 DNS label；单标签 localhost/example 拒绝；loader 不得静默规范化 Unicode 或非 canonical 输入。
- E-04：V1 仅 exact hostname；不加入 `allowed_subdomain_roots`；编译到现有模型时 `allow_controlled_subdomains=false`；未来需要子域须新任务/新 ADR。
- E-05：单个 policy 支持多个 exact hostname。
- E-06：redirect 使用主 `allowed_domains` 集合，无独立 redirect allowlist；HTTP→HTTPS 需目标 scheme/host/port 全部被 policy 允许；HTTPS→HTTP 始终拒绝；跨主机 redirect 仅当目标 host 显式存在于主集合。
- E-07：显式 `allowed_ports`，整数 1–65535，非空/唯一/升序，key 与 `allowed_schemes` 一致。
- E-08：配置使用 `allowed_schemes`，仅两种 canonical 值；编译规则 `["https"]`→`allowed_http=false`、`["http","https"]`→`allowed_http=true`；不修改现有 OutboundPolicy 字段。
- E-09：只禁止出站安全字段被环境变量/CLI/site 覆盖；MYSQL_*、Redis 等基础设施 env 不受影响。
- E-10：拒绝 unknown field、duplicate key/policy/hostname/scheme/port、null/bool/数字冒充字符串、policy 引用不存在、site 内联 override、非 canonical 顺序、scheme/port key 不一致。
- E-11：现有 5 站一次性显式迁移草案（见第 6 节）；不自动生成/扩展 policy，不保留旧回退。
- E-12：新增配置级共享 fixture；Python/Go 生产 loader 必须真实消费同一配置并各自负责本进程启动验证；E-B 只冻结 fixture。
- E-13：V1 配置与运行时目标均禁止 IP literal；不修改已封板 classify_ip。
- E-14：`config_version` 精确 `"1.0"`；回滚通过 Git。
- E-15：出站进程启动前完成验证；豁免进程写入文档（见第 7 节）。
- E-16：启动期交叉校验 site.json 静态 URL 与引用 policy（domain/base_url/api_url/page_url/搜索 endpoint）；动态运行时 URL 仍需每请求重验。

## 5. 生产接线阶段归属

当前事实：Go 生产仍用 RestyFetcher；Python legacy 仍走旧 requests/httpx；Python v2 probe 未用 D3 执行器；SecureHTTPExecutor 无生产调用方。TASK-022E 只负责配置合同、loader、启动验证、站点迁移；生产 HTTP 路径接线不得在 E-B 实施。

后续硬门禁：Go v1/v2 fetcher、Python legacy/v1、Python v2 probe/adapter 必须使用安全执行器；redirect 逐跳重验；每请求 DNS 全地址校验并 pin；不允许 v2 安全、v1 裸奔长期并存；接线完成前 deployment 保持 BLOCKED。DNS rebinding 防护与 legacy/v1 全覆盖由 ADR-016 及 C/D 阶段冻结，不是新决策。

## 6. 现有 5 站迁移草案（不修改 site.json）

| site_key | canonical hostname 集合 | schemes | ports | 建议 policy_id | 多 hostname | HTTP | 备注 |
|---|---|---|---|---|---|---|---|
| czj_beijing | czj.beijing.gov.cn | https | 443 | site-beijing | 否 | 否 | |
| czj_hangzhou | czj.hangzhou.gov.cn, search.zj.gov.cn | https | 443 | site-zhejiang | 是 | 否 | 共享 search.zj.gov.cn |
| sxcs_shaoxing | sxcs.sx.gov.cn, search.zj.gov.cn | https | 443 | site-zhejiang | 是 | 否 | 共享 search.zj.gov.cn |
| sc_czt | czt.sc.gov.cn | https | 443 | site-sichuan | 否 | 否 | |
| sd_czt | czt.shandong.gov.cn | http | 80 | site-shandong | 否 | 是 | 必须显式允许 http:80 |

规则：不因动态文章 path 自动开启 subdomain；未来发现新 hostname 必须先更新并验证 policy，不能运行时自动加入；迁移执行前需人工确认每站静态 URL 清单完整。

**迁移草案声明：** 迁移草案中的 hostname 清单目前仅根据 site.json 静态字段及已有本地样本整理，尚未完成全部站点真实搜索结果、文章 URL 和逐跳重定向 hostname 的联网验证。除现有北京样本外，不得把该清单视为动态出站 hostname 的完整证明。后续真实 hostname 审计需要另行取得联网授权，并必须在站点迁移或生产接线封板前完成。E-16 只检查静态 site 配置，不替代动态 URL 每请求重验；本任务不访问外网补证；exact-only 决策不回退。

## 7. E-15 进程清单

必须启动期验证：go-spider CLI v1/v2、go-spider 可触发抓取的 API/Worker、workers/search_worker.py、main.py CLI、其他实际创建生产 HTTP 客户端的进程。

豁免（写入本文档）：workers/parser_worker.py、Python FastAPI api/server.py、纯 monitor/metrics 进程、其他经静态审计确认无出站能力的独立工具。豁免名单一旦未来新增出站能力自动失效。

## 8. Loader 输入与错误优先级决策（TASK-022E-C-A-D / E-B-AMEND-1）

- 生产路径固定为 `config/outbound_security.json`，不允许 env/CLI/site 字段/运行时参数覆盖；复用现有项目 config-root 定位规则。核心内部 loader 允许显式 path 参数（fixture/单元测试），不暴露为用户 CLI/env 覆盖；生产 wrapper 无 path 参数。
- symlink 允许，但最终目标必须是可读普通文件；打开后读取一次；broken symlink、目录、设备、FIFO 等返回 `config_unreadable`。
- 每个出站进程仅在启动时加载一次并使用不可变字节快照；不监听、不热加载、不在请求期重读；本阶段不设计 reload API。
- JSON 输入边界：路径不存在=`config_missing`；不可读/非普通文件=`config_unreadable`；>1,048,576 bytes=`config_limit_exceeded`；空文件/BOM/非 UTF-8/注释/尾随逗号/malformed/尾随第二 JSON 值=`config_invalid_json`；合法且深度>32=`config_limit_exceeded`；合法且重复 JSON key=`config_duplicate`；顶层非 object=`config_invalid_top_level`。深度定义：根 object/array=1，每层+1，scalar 不增加，最大 32，只有语法完整合法后裁决深度；读取限制为 MAX_BYTES+1，不能无界读入。
- 生产 loader 只返回第一个稳定错误，不返回错误集合。安全错误对象只允许 reason/field_path/policy_id（适用时）/canonical hostname（合同允许时）；禁止原始配置、完整 URL、path/query/fragment、Authorization/Cookie/token/credential；底层异常仅作内部 cause。
- 全局验证顺序：路径存在 → 可安全打开为普通文件 → byte 长度 → UTF-8/BOM/空文件 → 完整 JSON 词法与尾随值 → 容器深度 → 重复 JSON key → 顶层 object → 顶层字段结构 → config_version → policies 数组结构 → 每个 policy 结构与类型 → policy_id → IP literal → hostname → scheme → port → semantic duplicate → config_conflict → policy reference → site 静态交叉校验 → 完成编译。
- 混合错误裁决：malformed+apparent duplicate=`config_invalid_json`；合法 duplicate JSON key+invalid type=`config_duplicate`；unknown+missing=`config_unknown_field`；semantic duplicate+invalid_type=`config_invalid_type`；IP literal+hostname 不合法=`config_forbidden_ip_literal`；unknown policy reference+site host uncovered=`config_invalid_policy_reference`；duplicate+conflict=`config_duplicate`。
- 确定性顺序：object 未知字段按 ASCII 字段名排序报第一个，missing 按 Schema required 固定顺序，field type/value 按合同固定顺序；policies 按文件数组输入顺序；site 按 site_id ASCII 升序；site 静态字段顺序 domain → base_url → api_url → page_url；字段含多个 endpoint 时按数组输入顺序。
- domain 必须是 lowercase ASCII 至少两 label hostname，不含 scheme/userinfo/port/path/query/fragment/root dot/IP literal，只做 exact hostname 命中。base_url/api_url/page_url 缺失/空串跳过，null/非字符串=`config_invalid_type`，非空必须是绝对 http/https URL，拒绝 userinfo/fragment/IP literal/root dot/相对 URL，hostname 必须已 lowercase canonical，scheme 必须允许，默认端口 http=80/https=443，port 必须属于对应 scheme；path/query 可存在但不参与 hostname 匹配且不得进入安全日志。先验证所有 site 的 outbound_policy_id 引用，再执行静态交叉校验。
- 双端责任：Python/Go 分别独立读取同一 JSON；两端均执行完整 18-reason 验证、从 raw bytes 检测重复 key、编译为各自冻结 OutboundPolicy；不通过 HTTP/Redis/DB/临时文件传递已编译策略；loader 不执行 DNS/redirect；任务级 allowed_domains 交集不属 loader，由后续共享执行器/生产接线阶段计算；空交集为运行时策略拒绝，不使用 config_* reason；快速/专业/legacy/v1/v2 均不得绕过交集；所有出站进程启动时 fail-closed，E-15 豁免进程不强制加载。

## 9. Logging 合同

允许记录：冻结 reason、稳定字段路径、policy_id、经合同允许的规范化 hostname、不含敏感内容的固定状态信息。

禁止记录：原始配置全文、完整 URL、path/query/fragment、Authorization/Cookie/token/credential 值、错误输入中的敏感字段内容、policy 完整内容。

fixture logging category 覆盖 6 个 case（l-001..l-006），使用明显非真实敏感哨兵值验证“不出现”；logging 允许 reason 集合同步为 18。


## 10. 受控重基线记录（TASK-022E-B-FIX2）

- B-FIX 前没有保存 96-case case-level 快照；`old96_missing=[]` 只能证明 ID 未丢失，无法证明原 96 case 的完整输入和 expected 未变化。
- R2 因此正确判定 FAIL；FIX2 不伪造历史证据。
- 经当前 104-case 完整语义复核后，以 R2 结束时的 104 cases 建立新的受控基线；本决定不构成对旧证据缺口的技术修复。
- 新基线只证明当前合同内容及 FIX2 之后的不变性；不把本决定描述为已恢复历史证据。
- fixture 与合同测试不代表生产 loader、生产日志脱敏或生产安全已经生效。
- production_logging_redaction=NOT_IMPLEMENTED。

### 封板证据口径（TASK-022E-B-S-FIX 修正）

1. Worktree raw evidence
- 工作区文件可能因 core.autocrlf=true 使用 CRLF；这些值只证明当时 checkout 的原始字节，不是 commit blob SHA。
- R3 工作区 E-B aggregate=`f540577223d0dfd06832b735be8a893212bab7f375ea278cbab71b938fa49ec8`（checkout 环境证据）。
- R3 工作区 fixture raw SHA=`6581704d4172c084d2d6f826bb6d76605c985dde44c8f0242f2cf5c2bd68c901`。

2. Git canonical evidence（封板权威）
- Git index/commit blob 是封板权威；`config/outbound_security.schema.json` 与 `tests/fixtures/outbound_security_config_contract.json` 在 index 中规范化为 LF。
- S 首次暂存后的 index E-B aggregate=`0f216a6ff4a9c44eb6590ee741c520e06b8ec319220146bb8ca3f75faf1d9ecc`（历史记录；最终 index aggregate 只记录在审计报告，不回写本文件）。
- canonical fixture LF SHA=`3abc41c3839d017852e9db34a976e1f12db2d5e6a58a68e8f0c3448fa1129a75`。
- Schema canonical LF SHA=`9b1969c01fa241506995df1ff276fcfda07856ed81405122cb330358a6d41656`。
- 行尾规范化不是合同内容修改。

3. Semantic evidence（worktree/index 完全一致）
- ALL104=`efcaded2a21eadce6a5c36167ac104c17fdf7e2487b80ea3e0cc63a4b0348f52`。
- NONLOGGING98=`1cdebf8ce767c7ce0897e973c3ecac4ec45f8299ed6a65811dc0fac1ab90f0cd`。
- LOGGING6=`8c8f5f1aa7a50c47015014bb111add7b9298339fe5e485ce9ea365a9cea955d8`。
- 上述 ALL104/NONLOGGING98/LOGGING6 标记为 `legacy_unversioned_aggregate`：来自 R3 历史审计，当时未保存足以独立复现的完整聚合 framing 规范，不再作为新 amendment 的机器验收值；第 10 节逐 case SHA 表仍为可信历史证据。
- case 数量、顺序、ID、输入、expected 与语义不变；R3 合同语义结论继续有效；原 96-case 历史证据缺口声明不变。

### S 失败记录（TASK-022E-B-S）

- 第一次 S 因旧验收规则要求 index raw SHA 等于 worktree raw SHA 而 STOP；停止与未提交行为正确。
- 根因是封板证据口径错误，不是合同、Schema 或 fixture 语义缺陷。
- 后续采用 index canonical LF blob 作为封板基线。

### 语义指纹（受控基线）

- 全部 104 case 规范化聚合 SHA-256：`efcaded2a21eadce6a5c36167ac104c17fdf7e2487b80ea3e0cc63a4b0348f52`。
- 98 个非 logging case 规范化聚合 SHA-256：`1cdebf8ce767c7ce0897e973c3ecac4ec45f8299ed6a65811dc0fac1ab90f0cd`（与 FIX2 开始前一致）。
- 6 个 logging case 规范化聚合 SHA-256：`8c8f5f1aa7a50c47015014bb111add7b9298339fe5e485ce9ea365a9cea955d8`。
- 上述三个聚合值为 `legacy_unversioned_aggregate`，保留 R3 历史记录，不作为新 amendment 的机器验收值；逐 case SHA 表仍为可信历史证据。
- 规范化算法：按当前 fixture 顺序选择 case；每个对象 UTF-8 JSON；key 排序；无多余空格；Unicode 不转义；哈希完整 case 内容（不只 ID/reason）。

### 逐 case 规范化 SHA-256

```text
v-001 59498afa4fed4d8b92c4b217dc76e57d08823426f8cffa2828a0b9d66c023921
v-002 f32e7ae0c86876384cc514af7e4f46fa1c9576d6ec30eec191c6c95163032d3e
v-003 7c3595d414f8dd5613c451b5aac1fc39747fcb84945310a4d4b4eff5b482e8f6
v-004 195bb318b84af3822bc7921dbbceef35f0cef8ed413d6236f32613ef61169b2c
v-005 ee2d01ab0e555563f9bcc8b031d3ff2a708fe206441e4c8b3a031d28c02330d2
t-001 32577a5294f54fbb45fd88e1245013773b5c1ed9836ae18676cc68c0d7a922b5
t-002 a2d458be8f1b1c0bd9ca0c51eec5691f22991030c4204d52c308d66087fd8af4
t-003 27d33e64fdf1b21eb9dc73fd05ceb1d204aeb49f6d0eb12afb3f6f38eb2eb941
t-004 3852af539b1bc9634da20af600f68343df4ee670c0563316b6e84822df7ba879
t-005 084cdf7fcb31c9da12ce882ee8c6b8ac9ea34f5cebb51cdf2a9fe8f09178b86f
t-006 2b7f1e552cfce0e4cef4fd385b964234874c4a2cc0b7acf6a9552959f6027e72
t-007 6b20c37b192c6612ed1c2bf76059df5cd37e5735baab5b54e95369daddf6c486
ver-001 65196d398f023f9875bdf593ac0def4b6ec7a4b2d40954e417d1bd1fa369c0a6
ver-002 31b35830fc4a565c624d70be3c21f7c95529400255d346683b84426d5a0aad83
ver-003 5ff23879522951099e3d6d44f8f74884905f23e29ebb64b17ed63efea5066806
ver-004 ab2fe53b299875e8264ed9f42790218d6f727f239db13cdb646eb6014492deb1
ver-005 0bb0d7bd1995374fe5d6d2f9e58ef6d7c3c069989aebd70182996cf80d1590eb
ver-006 5a2637e3b383565b044207fbc29ad1aa227775d879bb8bf38257e146ba5f7556
ver-007 af3cfe553ebada6060c9e5522bbb1dc46103eabfa5e28bf10bc45b99df4c107b
pid-001 8acb5ee66a5d4864b54c0afdcc9dc7093566cc242c85c4bb1ed3c0a1978f918c
pid-002 2856c447d5aad60f3c7e0b67a9ecf9ccda11403135f72cc54ae5e8c9d486a072
pid-003 287d39253900d3fa8f26400bf019168526e726befac7e61e59c832d45227e2f9
pid-004 dc10fb2a3ef84b3aac4d413cabf205f53b256f5f4baaa3302a95afb9e1f9cabb
pid-005 b635e6ad1b130059b72a0fa2ea835a4bce1ee6039f261643f3d6dd16e204fce4
pid-006 4f28038a71997a9964b292b9e3634ef53fa82217149065886dfdfd7b445894f4
pid-007 2264d2b55c9e31fb4fe1097b8e9554c2dd1973eca49eb105db2e83082a938dfb
h-001 adebc6e8e4f52a4caff7f91d0e032da2ac2ac7c20e9f34a513da55e4d431a86c
h-002 d23009b730b1c366dff69f711e02a73fda14b58385c72c2205d2924a09a120b0
h-003 c437b619d7eaa4fc677e0731184ff52170180127f68840a172dfadcaf0c5fd69
h-004 c37328f6f283df0464678b157ca5d6312aed36e834f29f39c8ceb3996e3f5726
h-005 eae6924cf279a8b09583deb1c73b9ad56f6d2bc8d30f705f5008cdbb69c7f7fd
h-006 c723dbe432e552d5825d8890f1a612a9fbbfc44b7715238370de66b93a16a5e3
h-007 c366a1ca4c74b33b31f906a9ab07ef907d395eab6bd8325ccfd8811f716d9943
h-008 f97650bc76529703a55ca3a45c33edc2718c4f08a414df6e5be0e79c2a8c7e5a
h-009 6e60431f4da5a447ade806222abd929acef5bc27e542788dbdea6fd5107d374a
h-010 53f0b549b2081ea8d425f98094422c32bd10f75229564bed92162ab79812d25e
h-011 b47f3e311cc2aca9ad5d1952939ddebb4a23ca21229b2bf179752406bcbb4d50
h-012 9ff221e163740ab3586033c25cb3dbe2fa2558c79ffa7348dbe30cd4f7a11bf7
h-013 b4fec6df556d75f2929980d4ab01f2d168d8b277ca64393c4693b6fd6499f71a
h-014 598d51d80e168dff011f7bf9e55e806f69583b97cc04cd1518059b52e9aaa61e
h-015 b95abd8df5e287eb739b08f80363b9385f6bec551fdc8b240b077406b13d7b64
h-016 2dc8038f2bda6b03148f338dde3898eda9d5659e2fbcfed44ab63af24c69f51e
h-017 64b9213c3fcd39dc20ac95ef1126f1dbbd8c85555e46be89ecb2d34486a3fd1f
h-018 1bf4190643ccdcdb9ef6b0b82ed6fdde34360b3489d6ad574d3675bca58c78e3
s-001 c4f8686f105d58b0dca54f91c054a0af1fc4e873569fe1da3b33d9369bf0d66b
s-002 558c49afb77e2823dd90a04094b842741ae4542eae4650bf9d6139858e976c19
s-003 0d7337bee33e8f0127eec85d69715fd025d6f1807cf476d65ce35d314b9bf0dc
s-004 912bc06e2c3edd550f719f75bbdcfa974f2a44590b3921803e03ed59a078cd11
s-005 a9d81f2326debe0b4c767dc6766aa9ee618c25b0a25aa7b3c9e21e090f53daa6
s-006 b562a507c32a201f72590321ac6d198d94e7cc3f77a9e5541f2498893694a22c
s-007 38f3f09b6196d1f7898a7bdc4cbe03ba41d93295267b3db391cf082666b01263
s-008 a493d7321078fe4f700f569f42e8f89560cebe3f66fa88a597fe68d077efc33c
s-009 e7971261114ee724e9d6a6ab99374f16be00dd62196fa4d429c0a1d625f7033c
s-010 73f2c62130decc1836fe0a4c8abf10f8e975d188ada05b50e5c7ae30f7e95fe1
p-001 a776d568952362bec4ba10405d87630bc490ee507d4ac285b174162b01b075be
p-002 f4e872af7c51f9e249cbab427f79d3935157c047fe60af21c1862e4e84023b6e
p-003 97453effa61e750bc7748a28a6844ab9345eb15e924c43b831115fcf63eab766
p-004 4ed0c899258ba53fe64eaf92b2b243281f9dbd0cfe8fae4b5c6ba76bcc38fd50
p-005 6071f4b54bf605d07e98e121b0a46b2e92213884f1b2a59cd689de3ccec5c682
p-006 be0f1d3ae0b656e04d76e33b8b2f7208275760a9608bc9379a4467a78c354505
p-007 a45060ad83fa02bff8ca8c0a45885011fd966c8608e5da94fecf2ec430b1db2d
p-008 2571c4a740b66bfd8063097a97d5e63d5921037103492de8b91c514479645396
p-009 6f6e8a6715a482a61f47357fcdabcfa4247fdc36c8278bbc08289c67d017f15c
p-010 f979e9a60a4685d0e9a5ecf1042c2bad64af267c0bf121c020fa7fe833466a88
p-011 b70b49153cde39b8f2b695fc6147029affbc99cc73c1c6089eec62603afb0abc
p-012 ecd3170c788b779d351fe4e66cca65492c13600292f7a46e8f6ac63ebab7dc7e
d-001 0eafb0ee4df6198787e4d3549d09da74eb6cdf9a7d654c922090c6363a45367a
d-002 13a27d684b8b2036d58f6c379c0c73416b79144b72996783284dd1c3db44a21a
d-003 794210a1bb2a23a04c3e4f4408907df7872fa180630bfb5f030139e8a3d2cda4
d-004 355a3fc135a45528f86fc45b253987502f3c72471a598c5f0d020eb1a52c941e
d-005 fcfc77b27fe2e5df7e54d863ec94de59b4d8bb9da704304cd30115df89caa704
d-006 eefb82f5087719831c7a17cdc96f62dff8cfd901947c973fb0fe9085463af3f8
d-007 3d8e4ce85de8740bfb542a2732451fc14fbeea0759d8b067343d3dc0c7a13d53
pr-001 bc8d76a242a5ae770e99f6c488ea51b58807c61b1811ba7d571240e3b680bbce
pr-002 5db6500f520e79a4bf4f3e1114d97fc5ccc91e004c6ef54e979ac1f65ae79834
pr-003 2948c6e49c2b44ecc64a54f73665408c9ddf138f0be41264ef498c8a3fa56c34
pr-004 78dd1cb8a11d40706b0bad9664e620f6c877b333567063afe53450236fc690b8
pr-005 cb701e0f3bb2ed4afccfb5593c9d28c5434fb817e0af813408eea786779566d2
sc-001 9b7923ca09147f32f910e3b241ac255120c75c96544a8da5a4abc836d5596e5b
sc-002 225ef6d5401965912f452c9df86493d6d27a8e518186b3011c1ab841f94dcff3
sc-003 f87dd2d8211110e74015450af1f9629bed1c9503815cfdd3a80267f7bf87ed91
sc-004 8e75d5445c96543c3405bb05f50358609581d04a1f92553eb30a6e0b84827f6c
sc-005 471f93d9b597884d58ffb264fe5ac2dc862097b810d6f88ab3a9f59271d49f2d
sc-006 ea9cbf1497edb3050b3c738c94b125dcd80ba8c16fd888b14fcecd0a3e4aec3e
sc-007 0b9321ae35b73cd31eb30ba28593909e61bc29e7fd540c46e5f72610c421c761
sc-008 34d2883008e8807d05082bf3eae680dff027d60f4dd8197a7b62e98ef698c371
l-001 806a46a5e352aee3e1fcce4f6e1a71a87510eafc76835f152ca80c67f6a28380
l-002 0f1ad09f4430746db442dafffc7598547eba6a40e215c9ee120c8f21ea2fd745
l-003 cb6c647b3ebb1a6294bc092434805e011335dde8d6939518a720aa70ded170d6
l-004 11c7ce2d5e051e565951b512d86ff251528069b66ea9cb4967910aed213000b5
l-005 6d5b3402345d2a39b958fe9b42ced689cf4176fde00cfe06db4c7c46b054d3e1
l-006 69929e243efded2074bc0ad687a680594da0073854811ea3137121178cd017a6
f-001 1c0710e97627a1f7658bf7b9b5c209ff3bd9f24f99b626563b449de4a424f482
f-002 1f6adeb8065e9bf82a3a8dcd724f6e242e37a03b48fe35745eef7d273b5892a1
f-003 ebbe702a2999539d51c11db8be9cb17db05178b7cd627b5079eb368653a98225
f-004 8402c73c3eec826331c6722c2553c2b7e015330d7874ed4542aaef9a2d16786e
f-005 afcc5461529e177051a265ca7016510954ef971b93ab7c1be0415c46e1528f12
f-006 6e12a5761fad8f4023fc445a54db77f531a6d2dff34253496c2f2435ff2bb6fb
f-007 522bb9527155350e6ad3b844b370c4349d1d42d218e4c9a1f8b9794eb7c55459
f-008 d94eb835aa2d4c91a39342c038edafc4fec9638820bd78974be2d769b4838b66
f-009 3e4b61dd2252f68a241fb3a58c9be111d791abafa9511d8272772f36d12ba96b
f-010 ed1419aaf4a7b813535a0b318988762d794cd174f9bda9078155a4732e447f23
f-011 c3cbabc58c5269e1d3849b5bbf446957ae76b5c5b5741858c750f6bd37921713
f-012 abcd538556b461dd52bb0572ffa0261bd880387e152eea4bfeb6edba0349b408
```


## 11. E-B-AMEND-1 决策指纹（TASK-022E-C-A-D / E-B-AMEND-1）

- aggregate algorithm：`OSEC-CASE-AGGREGATE-V1`；字节流为 `MAGIC(ASCII "OSEC-CASE-AGGREGATE-V1"+0x00) || COUNT(4-byte BE uint32) || CASE_1..CASE_N`；每个 case 为 `4-byte BE ID 长度 || ID UTF-8 || 32-byte raw SHA-256`；case 按 ID UTF-8 字节序升序；最终 `SHA-256(MAGIC || COUNT || CASE_1..CASE_N)`。
- 工作区 raw fixture SHA：`6de5f0e04816e19fcba6106a05af6ad30debffba1b87f309f0597989f0cc12d6`
- canonical LF fixture SHA（CRLF→LF 规范化）：`8d8b12f5f030dea6face5e2b25795f667657873bd4dd89a178659e0daabdcb45`
- BASE104_V1（104 个历史 ID）：`bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8`
- NEW21_V1（125-104=21 个新增 ID）：`dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850`
- ALL125_V1（全部 125 个 case）：`75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b`
- 原 104 case 规范化聚合（legacy，沿用）：`efcaded2a21eadce6a5c36167ac104c17fdf7e2487b80ea3e0cc63a4b0348f52`；BASE104 逐 case SHA 与第 10 节 104/104 一致。
- 旧草案值 `ALL125=2aeca26e90ee6aa79fb91fd6968dacdb23834d3a01350c6d54a4e8ad9356d3e6`、`NEW21=189612b6a29378781ae216fca0e627f760815d28c507080f1fbbac8c6ed9d94a` 标记为 `REJECTED_UNVERSIONED_DRAFT`，不再作为权威值。
- reason_count=18；fixture_case_count=125；12 category 不变。
- amendment=IMPLEMENTED/UNCOMMITTED；loader_decisions=FROZEN_PENDING_REVIEW；production_loader=NOT_STARTED；site_migration=NOT_STARTED；production_client_wiring=NOT_STARTED；deployment=BLOCKED；next_task=TASK-022E-C-A-D-R。
- 原 104 case 逐 case SHA 与第 10 节指纹表完全一致；新增 case 仅追加，未修改原 104 case；聚合元数据不计入逐 case SHA。
