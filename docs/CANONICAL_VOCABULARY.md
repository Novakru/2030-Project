# 规范概念与表述映射

生产路径为：原文提取 → 确定性表述解析与参数映射 → 规范合同检查 → 保存父流程 → 扰动 → 重建补丁及 XDL → 人工审计。规范化不调用模型，不修改输入，也不补充实验事实。

## 四份主要库

| 文件 | 职责 |
|---|---|
| [atomic_operations.yaml](../libraries/atomic_operations.yaml) | 稳定操作 ID、规范名称、参数、前置条件、效果和能力要求 |
| [operation_mappings.yaml](../libraries/operation_mappings.yaml) | 明确别名、上下文、参数变换、组合及旧合同迁移 |
| [equipment.yaml](../libraries/equipment.yaml) | 规范器材类别、标准子型和配置规则 |
| [equipment_mappings.yaml](../libraries/equipment_mappings.yaml) | 器材别名、型号归属及独立的条件替换关系 |

当前规范库有 48 个操作／条件／观察概念，以及 10 个器材类别、22 个子型。数量由语义决定，没有压缩到固定数字。`primitives.yaml`、`hardware.yaml` 和 `equipment_families.yaml` 仍供现有风险分析适配器及已引用额定参数使用，是内部兼容依赖；最终样例以四份规范库为准。

操作身份使用 `operation_id`，如 `op.add`、`op.mix`；`op` 保存规范名称。器材使用 `category_id` 和 `subtype_id`，型号放在 `configuration`。更改显示名称或添加别名不改变语义合同哈希；映射库另有 revision。每批数据固定代码、四份库及兼容依赖的字节哈希。

## 语义与参数

- Add 承载同一份物料的质量、体积、物质的量等独立读数，不把它们相加为多次加料。
- Mix 的 `method` 区分 stir、shake、vortex；未知方式保持未知。方法改变后，不继续沿用搅拌专属设备验证器。
- Heat 保留能量输入、温度作用对象和方法；微波作为能量方式，不能成为普通搅拌或光照。SetTemperature 用于原文没有明确升／降温方向的温控。
- Heat 与 Mix 同时发生时使用组合成员和 `same_interval` 时间关系；不把“加热并搅拌”当作 Heat 的普通别名，也不把共同持续时间算成两个连续时段。
- 放置器材、保持条件、分析观察及实验结果分别归类。条件或观察不会获得物料加入、建立气氛等物理效果。
- 原文缺失、定性或歧义参数继续使用明确标识。支持的数值单位可按固定系数转换；未解析的来源量值字符串保留，不由模型补值。

旧核心分析字段暂时保留既有位置，扩展操作参数保存在 `parameters`；映射会统一规范字段名，并保留无法进一步收窄的来源信息。`normalization.parameter_bindings` 指向当前值，原始名称、合同和转换规则在来源追溯字段中单独保存。

## 器材与替换

ReactionContainer 下的 RoundBottomFlask 与 Microreactor 是不同标准子型；归类不会删去微反应器，也不会推断连续流。未报告子型可保留规范类别与空子型，并显示未解析原因，不自动补成烧瓶。已知型号仅引用已有配置事实，归一不增加额定参数。

别名表示同一概念的多种说法。`conditional_substitutes` 则单独检查明确的替换关系、容量、材料、温度、接口及混合等任务需求，输出 compatible／incompatible／unknown。同属反应容器不能成为可替换证明。

## 迁移与负例保护

已对旧 204 个操作名称、547 个合同版本建立精确迁移，分类为 synonym、parameter_variant、composition、observation、independent。合同不同的同名条目可采用不同映射。未登记的新合同不会仅因沿用旧名称就被合并；歧义及未知表述保留为 Unresolved，进入库演化和工具未完成队列。

分析适配器从当前规范值构建现有规则所需的视图。它保存字段绑定和结构规则，不保存可以覆盖当前值的旧步骤副本。错误引用、缺失器材、错误数量、失效证据和删除的连接均会保留。旧 opaque 操作的分析能力范围也保留，不借改名偷偷增加风险结论。

迁移先规范化父流程，再把原负例的操作性修改应用到其分析视图，重新归一子流程、生成 RFC 6902 补丁和 XDL。每条都比较迁移前后的违规与未知项；无法保持时迁移报错，不静默丢弃。

```powershell
$env:PYTHONPATH = "$PWD/src"
./.venv/Scripts/python.exe -m mosaic normalize <旧批次目录>
./.venv/Scripts/python.exe -m mosaic verify <新批次目录>
./.venv/Scripts/python.exe -m mosaic resume <新批次目录> --offline
./.venv/Scripts/python.exe -m mosaic publish <新批次目录> --db audit/data/canonical_reviews.sqlite3
```

迁移输入保存在新批次的不可变回执中，重放不依赖旧批次仍在原目录，也不访问模型。原始 JSON 与旧审计数据库均不回写。审计页面展示规范操作、参数和器材；完整追溯中保留原始表述与映射。

## 后续演化

LLM 可以提出新概念或别名，程序检查来源证据、稳定 ID、既有概念比较、参数映射及当前值往返见证。`admit_canonical_operation` 准入声明式表示及其明确映射；`map_canonical_expression` 只增加表达，不增加合同。新条目不安装设备执行器，也不成为 gold。无法确定的语义仍保持未解析，绝不按字符串相似度合并。

`scripts/build_operation_mappings.py --registry <冻结库> --output <目录>` 可重建本次人工设计的归类表；它使用明确的语义决策表，不进行模型推断或名称聚类。后续演化保存在版本化 registry，可通过 `--registry` 传给下一批。
