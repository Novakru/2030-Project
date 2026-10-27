# ACRA 与 MOSAIC：一手资料核查

核查日期：2026-10-26。本文区分外部项目事实与本项目设计建议；未运行作者代码，未下载大型数据，未复制作者实现。MOSAIC 指 Multi-agent Orchestration for Source-grounded Actions, Instruments and Constraints。

## 1. 来源与版本

正式论文为 Sebastian Pagel、Michael Jirasek、Leroy Cronin 的 *Verification and execution of the scientific literature via chemputation augmented by large language models*，发表于 **Communications Chemistry 9, 191（2026-04-03）**。论文描述文献提取、流程消歧、XDL 翻译及验证流程，并报告六个反应、两个机器人平台。[正式论文，DOI 10.1038/s42004-026-01993-w](https://www.nature.com/articles/s42004-026-01993-w)

官方代码本次固定至 **`723b1e282ba00c5aed1a087ba92422a3bc3ead7d`**，提交时间 **2026-01-22**，提交说明 `init`。本次核查时仓库只有这一提交；README 仍写四例，与正式论文版本不同。因此，论文结果以正式论文为准，以下实现判断仅针对该固定代码版本。[提交](https://github.com/croningp/acra/commit/723b1e282ba00c5aed1a087ba92422a3bc3ead7d)、[README](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/README.md)

## 2. ACRA 实际实现

| 关注点 | 代码事实与一手定位 |
| --- | --- |
| 入口与编排 | `acra/main.py` 的 `paper_to_xdl`（231 行）、`procedure_to_xdl`（508 行）是入口。文献路径显式顺序调用 `PaperScraper`、`Procedure_Agent`、`XDL_memory`，另有 `AmbiguityAgent` 和 `CritiqueAgent`。这是程序编排多个专职智能体，不能据此声称它具有任意领域的动态团队框架。[main.py:317](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L317)、[main.py:395](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L395) |
| 文档提取 | `PaperScraper.parse_paper` 顺序处理文本块，将已有 JSON 交给后续提取；格式解析失败重试一次，结果使用 additive merge。配置的提取块为 4096 tokens；另以 2048-token 块保存文本嵌入。检索文本块并不等于每个提取字段都具备精确原文定位。[paper_scraper.py:235](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/paperscraper/paper_scraper.py#L235)、[paper_scraper.py:114](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/paperscraper/paper_scraper.py#L114)、[config.py:19](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/config.py#L19) |
| 消歧与物性 | `Procedure_Agent.get_chemicals` 识别化学品和歧义，可检索论文；`get_checmical_information` 查化学品信息及溶剂表，并在适用时换算摩尔量。`main.py` 可询问真实研究者并保存消歧映射。[xdl_generator.py:604](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/agents/agents/xdl_generator.py#L604)、[xdl_generator.py:667](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/agents/agents/xdl_generator.py#L667)、[main.py:410](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L410) |
| 有界修复 | `write_xdl` 默认六轮，先生成并检查 XDL，再执行一次 LLM judge，纳入修正后复查，最后执行仿真并将错误反馈给生成器。judge 的一次执行由 `inc_check` 控制；不能把它描述成每轮都会重新做完整语义核对。[main.py:34](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L34)、[main.py:123](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L123)、[main.py:184](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L184) |
| 硬件映射 | `map_to_graph` 调用 `chemputerxdl.graphgen.generator.graph_from_template`，开启 `auto_fix_issues`、`fix_reactors`，可接受模板。在已检查入口中，映射由程序和 Chemputer 工具完成，没有独立器材映射智能体或设备目录自动新增/合并流程。仿真实现调用 `map_to_graph(xdl)`，随后固定使用生成的 `graph.json`，并不是通用的设备事实维护方案。[setup_chemputer.py:9](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/laboratory/chemputer/setup_chemputer.py#L9)、[run.py:52](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/laboratory/chemputer/run.py#L52) |
| 证据与过程存储 | 主流程保存提取 KG、消歧映射、清洗流程、XDL 和错误日志；成功翻译才加入检索记忆。`save_to_labbook` 读取已有 JSON、执行 `dict.update` 再覆盖文件。它保存工作资料，但不是不可变事件审计。[main.py:426](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L426)、[main.py:480](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/main.py#L480)、[labbook_utils.py:129](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/utils/labbook_utils.py#L129) |
| 操作扩展 | `xdl_feature_suggestions` 将不支持步骤的描述追加到 `xdl_features.csv`。这是收集扩展建议，不是自动实现新操作，也不是自动收敛原子操作集。[xdl_utils.py:15](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/utils/xdl_utils.py#L15) |

## 3. 不直接照搬的行为

**外部代码事实：**流程清洗提示允许在知道或能够推断时补全精确条件；XDL 提示包含盐溶液默认水溶剂、密度 `1 g/mL` 的假设。[procedure_prompt.py:159](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/agents/prompts/procedure_prompt.py#L159)、[xdl_prompt.py:38](https://github.com/croningp/acra/blob/723b1e282ba00c5aed1a087ba92422a3bc3ead7d/acra/agents/prompts/xdl_prompt.py#L38)

**MOSAIC 建议：**将原文事实、可复算推导、智能体建议、未知条件分开保存。缺失值不能因为提示词要求精确而变成来源事实；图自动修正不能变成设备来源证明；翻译或仿真通过不能变成人工 `verified` 或 gold。每个修复版本保留父版本、原输入、变换、证据引用和验证结果。

## 4. 可参考的现成项目

以下是本次查阅的官方在线资料，不是已经安装、锁版或完成适配的依赖。采用前应锁定版本并对本项目样例验证。

| 项目 | 一手资料中的能力 | MOSAIC 建议及采用范围 |
| --- | --- | --- |
| Docling | `DoclingDocument` 统一表达文本、表格、图片、层级、阅读顺序、来源信息及可用的版面坐标。[官方文档](https://docling-project.github.io/docling/concepts/docling_document/) | 作为 PDF/文档解析的可选 adapter，借鉴“保留结构与来源定位”的产物。原始 ORD/JSON 继续直接读取，不能为了统一而损失原始字段。解析输出仍需保留原文件哈希；版面定位不证明化学语义正确。 |
| PaperQA | 官方描述将检索、证据收集与答案生成分开；证据过程对文本块排序、摘要和再评分。它也把图表的模型生成检索描述与原文分开保存。[官方仓库：算法](https://github.com/Future-House/paper-qa#paperqa2-algorithm)、[官方仓库：多模态](https://github.com/Future-House/paper-qa#multimodal-support) | 借鉴证据检索与事实提取分离、生成描述不污染原文。适合作为跨论文消歧的可选检索 adapter；不把问答摘要直接当作操作事实或风险标签，不因引入多智能体就要求全量向量数据库。 |
| LangGraph | 官方 checkpointer 文档说明保存运行检查点、恢复状态与中间任务写入；从旧检查点 replay 会重新执行后续节点，包括模型调用。运行级状态与跨运行存储是不同职责。[检查点文档](https://docs.langchain.com/oss/python/langgraph/checkpointers)、[持久化概念](https://docs.langchain.com/oss/python/langgraph/persistence) | 借鉴有界状态转换、检查点与恢复语义。初版可以用显式 Python 编排和本地运行产物；只有实际需要复杂分支、持久中断与恢复时再引入。工作流检查点不能替代审核事件，也不能保证模型再次调用得到相同结果。 |

## 5. 对本项目的设计建议

这些是建议，不是 ACRA 或其他项目已经实现的功能。

1. **运行 module：**用小 interface 承载一次数据集构建，内部完成来源读取、专职智能体调用、程序验证、有界修复、目录维护、扰动和产物发布。公共 seam 在“构建请求 → 可审核的冻结产物”，不暴露各智能体执行顺序；depth 带来调用 leverage，规则与验证集中获得 locality。
2. **通用与领域分离：**通用层只处理来源、证据引用、运行版本、任务结果、目录修订和发布清单。化学领域提供操作语义、设备能力、风险规则、扰动与导出。复用 `src/protocol_risk` 中已有计算；不把整套化学对象改名成通用对象后让所有领域继承。
3. **设备/操作最小集维护：**智能体提出匹配、新增、别名合并或宏分解；程序验证来源、参数一致性、覆盖能力和旧引用可迁移性。自动合并限于有证明的等价；能力或事实冲突保留分歧。修订可自动形成新目录版本，但不产生虚假人工决定。操作能由现有原子集精确表达时优先宏分解，无法表达时保留缺口与新增依据。
4. **扰动：**智能体提出目标风险和前置证据；程序执行单次语义变换，检查父例、子例唯一目标风险、精确 patch replay 与派生导出。硬约束失败、soft 假设与来源观测失败分别保留，不能换标签凑配额。
5. **来源与规模：**按文档、来源集合、设备能力和风险覆盖报告新增样例；别名、复制原文、控制场景和重新编号不增加独立真实来源数量。新领域需要实际来源和验证规则，不能由通用层自动宣称支持。
6. **审计发布：**输出独立审核包，保留原始快照、证据和智能体轨迹。`audit/` 继续使用独立 Streamlit、pandas 与标准库 sqlite3，通过明确导入读取新包；主依赖不引入界面依赖。旧审核数据库不随 JSON 更新，人工决定真实记录，silver 与 gold 区别保留。
7. **模型：**默认采用用户指定的 `terra` 配置名，由现有模型 adapter 解析。保存实际请求模型、返回模型、提示词版本、用量与缓存键；不推断该名称对应的上游模型身份。仅使用已保存响应可确定重放；重新调用模型是新的尝试。

本文未决定引入 Docling、PaperQA 或 LangGraph。是否增加依赖应由真实文档样例、恢复需求及可维护性验证决定。
