# 冻结版本的五条真实文本验收

日期：2026-10-30。运行代码：`2b5ca0d`，分支：`refactor/mosaic`。

**结果：0/5 条通过端到端转换验收，不能扩大生产数据规模。** 本次工程重构已提交，真实验收没有通过。下面的分析读取已保存的模型回执并离线重放编译，没有修改运行代码、提示词或库文件，也没有追加提取调用。

## 本轮实施范围

提取器输出统一的、带原文证据的 Facts；独立核对器检查全文与 Facts；格式修复和语义修复共享一次机会。库演化只对冻结的 Facts 补充映射或规范条目，再重新绑定，不重新提取。编译器生成通常的 XDL 文档结构；事实、规范 ID、证据与演化记录保存于配套 JSON，不加入新的 XML 树结构。

评价分为两层：程序检查实际 XML 的事实保留、绑定以及无依据新增；专家确认的完整参考用于衡量提取准确率。当前没有经过专家确认的完整参考，因此准确率为 `null`，批量使用门槛为 `false`。同一模型的核对意见不能替代专家参考。

## 输入与运行记录

- 输入：[五条原始实验文本](../examples/chemistry_holdout/sources.json)，仅使用 `Reaction.notes.procedure_details`，未从 ORD 的 inputs、conditions 或 outcomes 拼装流程。
- 来源与局限：[选样说明](../examples/chemistry_holdout/README.md)。五条来自未在历史开发集使用的 dataset group，但未证明严格的出版物级隔离；远端行服务版本也未独立确认，不能称为严格盲测准确率。
- 运行：`outputs/mosaic_cacb2c9e1fd05c77bb2d/`。
- 配置：`gpt-5.6-terra`，5 workers，17 次调用、900 秒的配置上限。
- 原调用中断后，使用同一冻结运行的 `resume`，已有回执被复用；期间未改代码。

| 指标 | 结果 | 含义 |
|---|---:|---|
| 输入 / 有效转换 / 失败 | 5 / 0 / 5 | 所有输入均在分母中 |
| 已保存的模型调用 | 12 | extractor 5、verifier 1、repairer 5、library curator 1 |
| 已保存调用的 tokens | 112,199 | prompt 77,746；completion 34,453 |
| 实际进入独立模型核对 | 1/5 | 其余四条在 Facts 校验阶段终止 |
| 新规范操作 / 新器材子型 | 0 / 0 | 本批未验证真实文本中新操作、新器材的完整准入 |
| 新表述映射 | 1 | `treat → op.contact`，silver；需专家核对 |
| 专家准确率 / 批量门槛 | null / false | 尚无专家确认的完整参考 |

**计量限制：** 12 次、112,199 tokens 是具有持久化回执的计数。中断时尚未完成的请求可能已在远端执行，无法由本地回执确定总计费次数与用量。`evaluation.json` 的 `wall_seconds=74.203` 仅对应恢复后的执行段，不是整批总耗时。当前实现没有完整持久化在途请求及跨恢复的时间预算，因此上述配置不能证明跨中断的实际计费／总时间上限。

## 五条失败的证据与归因

以下为实际阻断原因，不表示已经穷尽每条文本的全部科学错误。

| 原始记录 ID | 回执中的实际问题 | 判断 |
|---|---|---|
| `ord-0eefa53de79e45e78ff547734006edb6` | 初始时长为 `"1/2"`，不满足仅接受十进制的类型；修复后温度为 `value="0", upper_value="5", unit="°C"`，证据为 `at 0°-5° C.`，仍被数量字面校验拒绝 | 类型不能直接保留分数字面；温度区间的重复度符号未被程序识别。这是合同／程序覆盖缺口。修复图还存在产率 basis 状态与引用不一致，不能认为温度问题修完即整条正确 |
| `ord-158931abc49c434a86a39a133b41a3f5` | 初始图有重复 ID；格式修复后浓度为 `4 M`，原文证据包含 `(4-M)`，程序仍拒绝 | 初始为模型结构错误；最终阻断是程序未识别合法的连字符浓度写法，不是原文缺浓度 |
| `ord-e37c8de956f142e4847689cfe2cae743` | 初始图引用不存在的 evidence；修复后 `purge_bottle.participant_ids=["bottle"]`，但 `bottle.kind="equipment"` | 初始为模型引用错误。最终暴露动作对象合同缺口：设备可以是吹扫等操作的作用对象，当前 participant 仅允许物料／样品。原句中的吹扫对象也需保留歧义，不能凭常识改写 |
| `ord-8a5039f60afa42afa6418534e0bb4e31` | `20% by mole` 的组成事实在修复前后均为 `basis_status="reported"`，缺少 `basis_ref` | 模型未满足当前引用合同；合同也未清楚表达组成分数的分母范围。原文引用 Example 2，未提供的上游步骤必须标记未知，不能补造 |
| `ord-8841b6b409c7485da9c83fc3053ea8a7` | 唯一进入核对和编译的记录；接收悬浮液被作为第二个加料对象，三项接收液组分数量触发 `fact_loss_or_binding` | 提取角色、编译与检查合同存在共同缺口；另有乙醇证据定位错误及被拒绝的修复，详见下文 |

模型回执的定位：

| 记录尾部 | 初始 extractor artifact | 最后一次 repairer artifact |
|---|---|---|
| `…006edb6` | `artifacts/00010_687a63f0.json` | `artifacts/00013_a839511b.json` |
| `…b41a3f5` | `artifacts/00011_687a63f0.json` | `artifacts/00014_a839511b.json` |
| `…6cae743` | `artifacts/00012_687a63f0.json` | `artifacts/00015_a839511b.json` |
| `…0bb4e31` | `artifacts/00004_687a63f0.json` | `artifacts/00009_a839511b.json` |
| `…53ea8a7` | `artifacts/00002_687a63f0.json` | `artifacts/00006_a839511b.json` |

完整离线诊断：`outputs/reports/mosaic_cacb2c9e1fd05c77bb2d/receipt_diagnostics.json`。所有 artifact 路径均相对于本批运行目录。

## 真实的被拒绝 XDL：接收液被误当作加料

记录：`ord-8841b6b409c7485da9c83fc3053ea8a7`。原文描述将甲醇钠溶液滴加到已含两种化合物和乙醇的悬浮液，再搅拌两小时、抽滤、水处理、再次抽滤。

实际 Facts 中，`add_dropwise.participant_ids` 同时包含 `sodium_methylate_solution` 和 `suspension`，没有区分加入物与接收混合物。三个接收混合物组分数量也附在这个 Add 事件上。

下面是用**同一冻结 Facts、演化后的运行库、同一冻结编译器**离线复现的实际输出片段，省略其余属性。它未通过校验，**不是有效 XDL 样例**：

```xml
<Add reagent="15% strength solution of sodium methylate in methanol"
     volume="18 ml"
     concentration="15 %"
     method="dropwise"
     subject_phosphonium_salt_mass="25.4 g"
     subject_formylquinoline_mass="11.3 g"
     subject_ethanol_volume="150 ml"
     vessel="p_add_dropwise_vessel__NOT_REPORTED__"/>
<Add reagent="suspension"
     vessel="p_add_dropwise_vessel__NOT_REPORTED__"/>
<Stir material_1="mixture" time="2 hours"
      vessel="p_stir_vessel__NOT_REPORTED__"/>
```

错误分别是：

1. 第二个 `<Add reagent="suspension">` 多表达了一次原文没有陈述的转移。编译器把平铺的 participant 列表全当作加入物。
2. `25.4 g`、`11.3 g` 和 `150 ml` **并未丢失**；它们已在 XML 中，但接收混合物的组成关系没有可靠表达。检查器要求 Add 上物料数量属于该步骤的主 reagent，于是报告这三项 `fact_loss_or_binding`。直接放宽检查会掩盖额外 Add 的真实错误。
3. `ev_ethanol` 引用 `quote="ethanol", occurrence=0`。字面子串查找把它定位到 `methanol` 内的 `ethanol`，没有保证化学名称的词边界。核对器发现该证据绑定错误，但未发现前述接收液角色错误。
4. 修复器返回 `/graph/evidence/-` 和 `/graph/entities/5/evidence_ids`，而程序需要 `/evidence/-` 和 `/entities/5/evidence_ids`，补丁被拒绝。补丁还把后一次乙醇位置与 `occurrence=0` 搭配，不能仅改路径便视为修复成功。

完整诊断 XML：`outputs/reports/mosaic_cacb2c9e1fd05c77bb2d/rejected_diagnostic.xdl`；配套 JSON 明确保存 `accepted=false`。冻结运行的 `records.jsonl` 仍为空，诊断复现未被混入合格样例。

## 已做的验证及其适用范围

- 冻结前离线测试：174 passed、1 skipped；核心环境跳过可选 Streamlit 测试。独立审计环境的界面检查通过，包括显式数据库路径与多种独立用量展示。
- 冻结后 `mosaic verify`：哈希链、文件和五条失败覆盖检查通过；有效转换为零，不能据此声称 XDL 事实保留已通过。
- 冻结后 `verify_replay.py`：10 个输出文件字节一致、禁止 HTTP、0 次新增模型调用；证明本批产物可重放，不代表提取正确。
- 真实审计数据库的 AppTest：5 条均可逐条翻页；每条显示转换失败原因；0 个界面异常；检查前后均为 5 pending、0 次人工决定。核对器意见显示于相应记录，但它只是待专家确认的模型意见。
- 本轮真实库演化仅验证一个表述映射的准入与重新绑定；未重新提取 Facts。新规范操作及器材子型自动准入仍只有离线测试证据。

## 审计入口

```powershell
audit/start_review.ps1 -Database audit/data/facts_20261030.sqlite3
```

数据库中是 **5 条失败候选记录**，不是 5 条正确正例。原始 JSON 不会被审核操作改写；导出才将数据库决定合入 JSON，并自动生成时间戳目录。诊断文件保留在 `outputs/reports/`，原始回执保留在运行目录，运行数据与 SQLite 均不提交到 Git。

本轮已使用 Streamlit AppTest 检查翻页，没有执行任何“通过”“拒绝”或撤销动作。

## 下一轮讨论范围

本批结束后停止 API 测试与代码调整，先确认以下合同设计，再进入下一冻结版本：

1. 数量同时保留原文字面与语义值；统一处理分数、区间、单位标点，不把可识别的写法差异交给模型反复修复。
2. 事件显式区分加入物、接收物、组成、源／目标、作用设备等角色；编译和检查共同遵守这一合同。新操作与器材仍通过库演化，不逐样例增加提取分支。
3. 明确相对量基准和组成分母的表达；缺参或歧义为显式状态，不自动补充科学条件。
4. 修复器使用明确的补丁根与对象 ID；字面证据定位处理名称子串，并在输出前保留被拒绝的编译诊断。
5. 先用本批保存回执与独立语义断言检验这些通用规则，再补专家确认的完整参考；其后才能冻结新版本、执行下一批真实测试。

以上是下一轮建议，未在本次验收后实施。当前结果不足以支持大规模生产，也不足以声称系统已经自动适应新流程。
