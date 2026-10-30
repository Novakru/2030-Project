# MOSAIC 抽取、评价与演化组件调研

访问日期：2026-10-30。范围：纯文本实验流程 → 有证据的事实表示 → 扩展 XDL。
本次仅核查官方文档、官方源码及论文；没有安装这些组件、调用用户模型 API 或进行网关兼容性实测。以下选型与架构建议是针对 MOSAIC 的工程判断，不是这些项目提供的效果保证。

## 结论

优先采用三种机制：**字符级证据定位、独立事实覆盖评价、受约束的结构输出**。提示优化放在批次之外，操作和器材准入放在版本化库中。增加 Agent 数量不能替代事实真值、数量归属和编译保真检查。

建议保留轻量的 MOSAIC 运行时，不一次引入整套框架：LangExtract 可作为证据抽取的对照实现；DSPy/GEPA 可成为可选离线优化工具；结构输出根据网关能力启用。下面没有给出任何 MOSAIC 性能提升百分比。

## 1. LangExtract：原文定位与分块抽取

**官方机制。** LangExtract 从原文抽取结构化项目，回填字符区间；未能定位的项目可以没有 `char_interval`。它支持分块、并行和多轮抽取，并提供原文高亮。官方 resolver 区分精确、模糊和部分匹配，因此“有字符区间”不能一律当成逐字符准确证据。[官方仓库](https://github.com/google/langextract)、[定位实现](https://github.com/google/langextract/blob/main/langextract/resolver.py)

**适用问题。** MOSAIC 可以借鉴“先提取原文片段，再确定性定位”的证据层：每个物料、用量、条件和器材提及保存 `source_id/start/end/quote`；相同数字出现多次时保存具体位置。模糊匹配与精确匹配分开统计，正式事实证据优先要求精确片段。

**能力边界。** 找到了 `80 °C`，不代表它被绑定到正确的步骤；找到物料名，不代表所有用量都被保留。该组件没有替 MOSAIC 定义实验事实图、共指、时序或扩展 XDL 合同。额外抽取轮次也会增加调用，并不天然符合低延迟目标。这些是应用层需要验证的内容。

**网关与依赖。** 官方 OpenAI provider 接受 `base_url`，并把 schema 约束交给 `response_format`；没有 schema 时使用 JSON mode。安装 OpenAI 适配需要其可选依赖。由此可以确认存在自定义地址接入点，不能确认当前网关支持严格 schema。建议先用现有 HTTP 客户端实现同等 span 合同，把完整 LangExtract 作为可选对照，避免运行时重复一套编排。[provider 源码](https://github.com/google/langextract/blob/main/langextract/providers/openai.py)

## 2. DSPy + GEPA：指标驱动的离线优化

**官方机制。** DSPy 将程序输出交给可编程 metric 评分；GEPA 利用执行轨迹和文字反馈提出提示修改并比较候选。它支持将反馈定位到特定 predictor，并提供 metric-call 预算。它优化的是被测程序在给定评价上的表现，不能生成独立可靠的领域真值。[DSPy metrics](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/evaluation/metrics.md)、[GEPA 实现](https://github.com/stanfordnlp/dspy/blob/main/dspy/teleprompt/gepa/gepa.py)、[GEPA 论文](https://arxiv.org/abs/2507.19457)

**适用问题。** 将“丢失 71 µmol”“80 °C 绑错事件”“Schlenk 被降为普通容器”作为结构化反馈，优于只优化 XML 是否可解析。可优化事实抽取、覆盖核查的提示与示例；编译器、事实真值和准入标准应冻结，不允许优化器为了提高分数放宽它们。

**数据边界。** 显式分开 train（提示／示例优化）、dev（模型与配置选择）、test（冻结后一次评估）；同一来源或近重复流程不能跨集合。GEPA 的 `valset` 若未传入会退回 `trainset`，因此必须显式传入。当前反复调过的五条只能作为 dev 回归。未见五条能检查工程闭环，但不足以证明大规模泛化；后续仍需只读灰度及专家抽查。这是 MOSAIC 的评价设计建议。[官方 GEPA 指南](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/diving-deeper/gepa-in-depth.md)

**网关与依赖。** DSPy 文档提供带 `api_base` 的 OpenAI-compatible Chat Completions 连接方式，但模型标识、参数及可选引擎仍需实测。它可以离线运行后导出冻结提示，生产抽取不必依赖 DSPy。提示优化需要多次评价调用，不应在每条 protocol 内运行，也不能承诺比当前流程更省调用。[官方模型接入文档](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/programming/language_models.md)

## 3. 结构输出：区分服务端约束与客户端校验

| 组件／方式 | 能提供什么 | 当前 OpenAI-compatible 网关的实际边界 | MOSAIC 建议 |
|---|---|---|---|
| 服务端 JSON Schema | 支持该能力的服务可约束字段、类型和枚举 | 地址兼容不证明 schema 被执行；还要处理拒绝、截断及支持的 schema 子集 | 能力探测后启用；保留本地严格校验 |
| Instructor | Pydantic 解析、验证、错误反馈和重试；支持多种输出模式 | 客户端验证不会改变远端采样；工具／JSON 模式仍依赖服务端 | 已有校验与回执体系可复用其有界重试思想；不是必装依赖 |
| Outlines | 结构化生成及多种模型后端适配 | 不能由“支持远端 API”推导出能控制任意远端模型的 logits | 自部署推理或确有支持的后端再考虑；当前不为此增加依赖 |
| llguidance | JSON Schema／语法转换与生成时 token 约束，已有推理服务集成 | 必须在可控制的采样链路或集成服务端生效；客户端装包不能给现有网关添加 token masking | 暂作为服务端能力选项，不加入 MOSAIC 客户端运行时 |

依据：[Instructor 工作方式](https://python.useinstructor.com/faq/)、[有界重试机制](https://python.useinstructor.com/learning/validation/retry_mechanisms/)、[Outlines 官方说明](https://github.com/dottxt-ai/outlines)、[llguidance 集成和工作方式](https://github.com/guidance-ai/llguidance)、[llguidance schema 支持边界](https://github.com/guidance-ai/llguidance/blob/main/docs/json_schema.md)。JSON mode 只约束合法 JSON，和匹配指定 schema 有区别。[服务端结构输出说明](https://developers.openai.com/api/docs/guides/structured-outputs)

**共同限制。** 合法 JSON、Pydantic 对象或合法 XML 都可能丢事实、错归属、猜参数。结构合法率必须和事实 precision/recall、数量归属、时序及编译损失分开报告。schema 应允许 `NOT_REPORTED`、定性条件和多个独立用量；不能用单个字符串 `amount` 强迫质量、体积和物质的量互相覆盖。

当前仅能下结论“存在可用接入方式”，不能下结论“当前网关已经执行严格约束”。若后续测试，应独立保存能力回执；不支持时退回普通 JSON 加本地校验及最多一次修复，明确标记降级。

## 4. ACRA：分层检查、领域记忆和缺失步骤核查

**书目信息核对。** Sebastian Pagel、Michael Jirasek、Leroy Cronin，*Verification and execution of the scientific literature via chemputation augmented by large language models*，**Communications Chemistry（2026）**，DOI `10.1038/s42004-026-01993-w`；不是 Nature Chemistry。早期 arXiv 标题为 *Validation of the Scientific Literature via Chemputation Augmented by Large Language Models*。[出版社论文 PDF](https://www.nature.com/articles/s42004-026-01993-w_reference.pdf)、[作者预印本](https://arxiv.org/abs/2410.06384)

**已核查源码。** `write_xdl` 对生成结果执行 XDL 检查，再检查与原文不一致／缺失的步骤，最后可执行硬件图模拟。日志把 `syntactic_passed`、`translatable_passed`、`simulation_passed` 分开；缺少 Chemputer 时会提前返回并跳过这套迭代。入口另有 `expand_memory` 和不明确条件处理。[官方主流程](https://github.com/croningp/acra/blob/main/acra/main.py)

**值得迁移。** 将格式、源文一致性、平台能力分开；把原文对照核查放在编译检查之外；只有经过验证的样例才进入可检索记忆。MOSAIC 可以保留独立覆盖核查，但不让另一个 Agent 把整份流程自由重写。

**不能直接照搬。** ACRA 的成功样例记忆和 XDL 特性建议，不能直接当成已经证明了规范操作／器材库的自动准入。当前核查也没有证据表明其检查会自动量化每个源文事实的召回。Chemputer 模拟通过更不等于原文信息全部保留。完整 ACRA 依赖 PDF、网页、化学工具及 XDL 软件栈；其硬件与多领域扩展仍需 MOSAIC 自己实现、评价。[官方依赖](https://github.com/croningp/acra/blob/main/requirements.txt)、[项目说明与许可](https://github.com/croningp/acra)

因此建议借鉴检查分层，保持当前标准 XDL 的 XML 结构；新语义通过扩展操作和器材定义准入，聚类、证据、准入证明和迁移关系留在 JSON／库文件中。

## 5. LangGraph：可选的持久化状态图

LangGraph 提供状态化编排、持久执行和人工中断；它解决运行状态管理，不能提供实验事实真值或提高抽取召回的保证。[官方项目](https://github.com/langchain-ai/langgraph)

MOSAIC 已有回执、快照与重放，现阶段可用显式状态机表达同一流程，无需仅为多 Agent 接入 LangGraph。若后续确需复杂暂停恢复或分布式调度，再评价其替换价值。其节点仍可调用现有 HTTP 网关，但这不增加服务端模型能力。

## 对 MOSAIC 的建议合同

以下属于本项目设计建议，尚未实现或实测：

1. **抽取与命名解耦。** 抽取器输出有类型的事实、事件、对象与精确证据；不因当前库缺少某操作就遗漏原文动作。数量是列表中的独立事实，每个事实绑定物料与事件；定性条件保存原文，不猜数值。
2. **核查与生成解耦。** 正常路径为一次事实抽取、一次独立覆盖核查；按未覆盖事实和错误绑定生成局部修复，最多一次。核查器的事实清单用于运行时筛查，不能充当最终评测金标准。
3. **库演化独立于业务抽取。** 未知概念进入候选队列；每批有限调用提出映射／合同，程序检查类型、证据、现有语义、反例与往返见证。准入后确定性重绑定，不修改源事实；无证明则保留未解析状态。
4. **编译独立验收。** Facts IR → 规范映射 → 扩展 XDL 由程序完成；源事实、映射前后、XML 表达分别对比，捕捉中间保留却在导出时丢失的用量、器材子型、气氛和洗脱梯度。
5. **评价以专家确认事实为参照。** 至少分开事实 precision/recall、数量数值及单位、数量归属、事件／时序关系、器材子型、原文缺参的正确标记、编译信息保留、库准入回归；同时记录调用次数、耗时和失败率。空输出不能靠高 precision 得到通过。
6. **固定轮次。** 缓存回执验证程序 → 冻结代码、提示、库、模型配置及输入 → 整批运行 → 统一诊断。旧五条是 dev 回归；另选五条未见样例作工程闸门，随后只读灰度 20–50 条。程序缺陷进入下一轮版本，运行中不改源码。未过关时暂停并报告故障分层，而不是持续逐样例补丁。

只完成五条只能证明这些案例的闭环行为；评价数据的覆盖范围与独立性，决定后续能支持多大范围的可靠性判断。
