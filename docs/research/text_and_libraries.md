# 纯文本提取与可演化实验词汇库：一手资料核查

核查日期：2026-10-27。本文区分外部项目事实、本仓库现状与设计建议；以下建议不表示相应功能已经实现，也不表示跨领域、硬件替换或官方平台编译已获得验证。

## 结论

提取的唯一事实输入应是实验流程原文及其明确关联的文字上下文。ORD 可以承载原文、标识来源和提供独立对照，但结构化试剂表、温度、时长、加料顺序不能成为生成动作的隐藏输入。设备的功能分组用于缩小候选集合；是否可替换必须针对当前流程需求逐项判断。词汇库迭代需要真实的版本迁移与回归验证，不能止于记录建议，也不能把自动生成的解释当成人工认证。

## 1. 外部资料实际支持什么

| 一手资料 | 核实事实 | 本项目可复用的设计 |
| --- | --- | --- |
| [ACRA 正式论文](https://www.nature.com/articles/s42004-026-01993-w)；[固定作者代码](https://github.com/croningp/acra/tree/723b1e282ba00c5aed1a087ba92422a3bc3ead7d) | 论文发表于 Communications Chemistry，2026-04-03。流程从文献提取实验与分析信息、转为 XDL、进行具体平台的模拟与执行；实验展示为六个合成、两种平台。 | 保留提取、独立复核、歧义处理、硬件适配的分工；把“忠实转录”和“适配特定设备”作为不同产物。六个实例不能证明任意领域或器材的普适执行能力。更多固定代码核查见 [acra.md](acra.md)。 |
| [XDL 2.0 标准](https://croningroup.gitlab.io/chemputer/xdl/standard/)；[文件结构](https://croningroup.gitlab.io/chemputer/xdl/standard/xdl_file_structure.html) | XDL 将抽象化学操作与具体平台分开；文件声明 Hardware、Reagents、Procedure，可另含 Metadata。Procedure 可划分 Prep、Reaction、Workup、Purification。 | 原文的反应前准备、反应、后处理、纯化都要进入动作覆盖检查；不能只提取形成产物前的主要反应。抽象 XDL 文件生成不等于具体机器可执行。 |
| [XDL 操作规范](https://croningroup.gitlab.io/chemputer/xdl/standard/full_steps_specification.html) | Add 包含加料时长、逐滴、同步搅拌等参数；Separate 区分保留相、分离容器和目标容器；Transfer 包含清洗溶剂及次数。这些是不同语义维度。 | 合并操作或降成宏时要保留物料去向、相选择、速率、条件与重复；名字相近或共有参数不足以证明操作等价。 |
| [LabOP 作者仓库](https://github.com/Bioprotocols/labop/tree/develop)；[规范仓库](https://github.com/Bioprotocols/labop-specification) | LabOP 使用唯一 URI 标识 Protocol、Primitive 等对象；Protocol 的每次 Execution 可以有独立历史。ExecutionEngine 通过 BehaviorSpecialization 将协议解释为特定平台行为；无特定实现时可以采用不操作硬件的默认行为。 | 可采用带领域命名空间的操作标识，将流程定义、执行记录与导出 adapter 分开。借用这种 seam 不需要将 RDF、SBOL、整个 LabOP 运行环境加入当前轻量依赖。 |
| [Autoprotocol ContainerType 官方文档](https://autoprotocol-python.readthedocs.io/en/stable/container_type.html) | 容器类型分别描述功能、孔数、孔容积、死体积、可靠吸液最小量、工作容积与可能不同的实际最大容积；还记录盖、封膜、供应商和型号。 | 中等粒度的器材族可带可选参数与能力，具体规格留在型号/来源观察中。不能将标称体积当工作体积，也不能用整板体积代替每孔体积。 |
| [Opentrons 当前 Labware 文档](https://docs.opentrons.com/python-api/labware/)；[定义说明](https://docs.opentrons.com/flex/labware/definitions/) | 系统以明确的 labware definition 描述形状与交互；模块、adapter、labware 可以分层加载。旧的组合定义会限制部分功能；液体初始标注本身不执行移液，也不保证标注量符合容器容量。 | 保留设备组合结构，避免将“模块+夹具+容器”粗化成一个万能设备。引用某平台的库名或通过其语法检查，不能替代本项目的容量、材料和流程语义检查。 |

以上是公开文档核查，没有安装、执行或复制这些项目的实现。XDL 文档展示的是所链接版本，不据此断言所有新旧 SDK 参数完全兼容；LabOP 的 develop 文档可能变更，正式采用依赖前应另行固定提交。

## 2. 本仓库可定位的问题

以下为本次检查代码时观察到的现状，属于本仓库事实，而非上述论文结论；后续实现可能已修正。

- `src/mosaic/chemistry.py` 的 `eligible()` 同时依赖 ORD 的温度、SMILES、产率与有用量的 components；`text_ready()` 要求原文超过 400 字符。这会排除短而完整的实验原文，也无法接收普通文本文件。
- 同一 module 的 `extract(..., use_model=False)` 直接调用 `structured_plan(raw)` 并可能插入结构化气氛。它没有证明原文支持生成的步骤。
- 模型路径的设备 specialist 同时接收 `source` 与 ORD `setup`，因此只限制 extractor 的输入不足以建立纯文本隔离。
- `src/mosaic/registry.py` 支持来源观察、操作候选和完全一致合同的 alias；`compact_device_observations()` 只合并精确厂商型号与一致事实。当前缺少独立的常用设备族与按流程需求判断的替换结果。
- `src/mosaic/catalog.py` 正确声明“不是已证明的普适最小集”，但其固定 primitives 统计与候选收集不能单独满足用户要求的自动库迭代。
- `libraries/hardware.yaml` 同时包含器材类型、具体商品型号和平台模板。应明确它们的角色，避免每个容量规格都增加一个操作级设备类型，也避免不同物理过程只留下一个 `vessel`。

## 3. 推荐的 agent 分工与事实隔离

下面是依据一手资料和本项目目标形成的设计建议，不是外部项目的既有实现承诺。

1. **动作识别 agent：**只读取不可变 `SourceText`，输出完整的原文动作清单，覆盖准备、物料加入、条件、监测、后处理与纯化；每项带精确位置与原文。保留无法解析的动作与数字。
2. **提取 agent：**读取同一文本和版本固定的操作合同，建立有序流程。每个物料、用量、条件、容器引用须能指回原文；没有表达的顺序、常温、时长、密度保持未知。
3. **独立覆盖/复核 agent：**在原文动作清单与候选流程之间建立表示关系，区分 represented、context、unsupported、ambiguous。未表示的物理动作阻止“完整转换”发布，不能通过删除清单项解决。
4. **器材映射 agent：**只从原文观察到的器材出发，保留 `microreactor` 等原始类型；提出标准器材族、组合关系与当前流程的能力需求。泛名不产生压力、额定温度、接液材料等事实。
5. **词汇维护 agent：**聚合未表示动作、重复器材描述和实证冲突，提出 add、alias、group、split、decompose 等结构化修订。程序检查引用、合同、维度、已知状态效果和迁移回归，再发布新的不可变库版本。
6. **扰动 agent：**在已经检查的原文忠实 parent 上提出单次干预；程序保留精确 patch、适用前提与所违反约束。可程序化的扰动不需要反复请求模型。

ORD 对照应在主流程产物冻结后进行。对照 module 可以报告“原文 5 mL、ORD 10 mL”或“结构字段缺失”，但不允许反向补全操作。其输入/输出要与 `SourceText` 区分，测试时给结构字段注入矛盾信息并确认原文转录结果不变。

字符位置匹配只能证明某串文字出现过，不能单独证明数字绑定给了正确试剂、重复次数解释正确或动作全集完整。因此还需字段级引用、动作覆盖记录、规则核查及最后的专家审计。

## 4. 器材族、来源观察、条件替换

建议用三个不同概念维护库：

- **来源观察：**“该原文说 10 mL microreactor”。带原文、位置、运行条件，可能没有厂商型号。
- **标准器材族：**例如单容器反应、微型反应容器、多孔板、循环温控、加热搅拌、相分离、固液过滤。按物理用途和不可忽略的操作差异分组；容量作为参数，微型反应器不会自动归成普通烧瓶。
- **具体型号/组合：**可选的厂商事实与夹具、容器、温控器等组合；只有精确资料支持的额定值才进入约束库。

初始族应从现有数据观察及常用 Chemputer/通用实验器材归纳，避免仅为潜在未来领域填入大量商品型号。生物与材料领域的术语以后通过同一修订流程加入，不要把“通用”理解为提前批准所有过程。

同族仅表示相似候选。替换函数需要显式流程需求：操作能力、工作体积、温度作用范围、压力、材料相容性、密封/气氛、混合方式、光路、无菌/污染要求、连接和必要几何条件。返回 `compatible`、`incompatible` 或 `unknown`，并附每项证据与缺失项。未知事实不能当作满足约束。

例如，加热板与循环浴可同属温控候选，但不能因温度数字相近就替换；每孔板与单瓶不能只比总容积；`microreactor` 的名字本身也不能证明流动、耐压或传热性能。这些均是本项目保守推断规则，不能声称上述标准已经认证了所有替换关系。

## 5. 自动迭代应实际改变什么

自动运行可以进行：已证实别名归并、来源观察去重与聚合、标准族的新增/细分、证据支持的型号注册、无损宏的新增，以及通过合同验证的 IR 操作新增。每次输出 revision、父 revision、修订理由、来源、受影响案例和回归结果；旧数据仍固定旧版。

新增操作至少声明领域命名空间、参数及维度、输入/输出、前置条件、已知状态效果和引用。能由现有操作无损表示时优先做宏；不能表示时保持新候选的语义，不强塞成 Wait 或 Purify。源记录中的未知条件不能被操作合同默认值伪装成原文事实。

“支持 IR 表示”“有 XDL export adapter”“在特定平台验证可执行”是三个独立状态。自动加入 IR 操作不应使不存在的 XDL 标签或未经实现的硬件驱动获得执行资格。添加 exporter 必须使用受控、已有实现的 mapping；生成的任意 Python 或模板表达式不能直接执行。

操作合并的自动证明范围应有限且明确：参数不丢失、状态效果/端点一致、顺序和重复保持、风险检查不退化、历史样例和反例通过回放。无法证明的跨合同合并留候选。频率低不等于冗余；得到当前批次的精简集合也不等于普适最小集。

## 6. 优化最常见 caller 的 alternative interface

这是 codebase-design 的第三种设计草案，重点是让“给一个文本文件得到 XDL 与审计材料”的默认用法简单。它不要求将内部 agent 顺序暴露给使用者。

```python
runtime = Runtime.from_env()  # 外部模型依赖显式构造
project = TextProject(workspace="data/mosaic", runtime=runtime)
result = project.convert("procedures/example.txt")
# result.record, result.xdl_path | None, result.issues,
# result.coverage, result.library_revision, result.library_changes
```

**Module/interface：**`TextProject.convert(source: Path | SourceText, *, domain="chemistry.batch") -> Conversion`。默认启用文本隔离、来源定位、独立覆盖复核、器材族映射、可验证库迭代及原子产物保存。`Conversion` 明确区分完整、需补充、不能导出；不能导出时保留记录与原因，`xdl_path=None`。批量 CLI 只组合该 interface，不另造一套提取规则。

**不变量/错误：**输入原文不可变且有摘要；结构化参考信息不进入提取和设备事实；未知字段不补值；当前 run 固定库 revision。无文本、非法参数、版本冲突是明确错误；模型暂时失败可恢复；源信息不足是有原因的结果，不伪装成成功。每次转换只做有界模型调用与有界修复。

**Seam/implementation：**外部 seam 是“原文 → 带证据的转换结果”，内部隐藏动作清单、专职 agent、合同解释、库迁移、XDL mapping 与审计快照。正负样例生成复用 Conversion 中的 parent，不能绕过它再从 ORD 生成 parent。

**依赖/adapters：**维度、引用、覆盖检查和受控库迁移是 in-process 规则，直接测试；文件与 SQLite 是 local-substitutable，使用临时目录和临时数据库验证；模型为 true external，通过显式 completion interface 注入真实 HTTP adapter 或可记录/回放 adapter。领域合同与 export adapter 位于内部 seam；只有确实存在第二种实现时再抽取通用 interface。

**Depth/locality/trade-offs：**常见 caller 只需 workspace、runtime、文本路径，获得完整证据产物与可审计失败，depth 高；文本事实隔离与字段引用集中在一个 module，locality 好。代价是高级 caller 不直接安排每个 agent，且 convert 既做计算又保存不可变产物；需要分布式调度时可以以后将同一结果与存储分离，不应现在向 caller 暴露一组易漏执行的步骤。

## 7. Biology / materials：当前 seam 的用法与尚缺的 adapters

当前可复用的是来源证据、角色调用、库修订记录与版本化发布。`Runtime(domain=...)` 已允许注入不同的领域 implementation，`CurationPolicy` 允许提供领域自己的合同验证；这不表示仓库已经提供生物或材料实验的提取器、XDL exporter 或设备驱动。

下面的例子使用当前真实存在的 `maintain_library` interface，演示两种领域的动作如何进入有来源的语义候选。原文和 curator 响应都是**手写的文档测试输入**，不是模型提取结果，也不是新收集的实验数据；`RecordedCurator` 是本地 adapter，不发出网络调用。

```python
from types import SimpleNamespace

from mosaic.evidence import SourceSpan
from mosaic.evolution import CurationPolicy, maintain_library
from mosaic.registry import Registry


class RecordedCurator:
    def __init__(self, name, parameters):
        self.name, self.parameters = name, parameters

    def model_call(self, role, system, payload):
        origins = [item["observation_id"] for item in payload["observations"]]
        return {
            "model": "local-documentation-fixture",
            "data": {"proposals": [{
                "action": "cluster_operation", "origins": origins,
                "name": self.name,
                "reason": "Needs a domain contract; no validated exporter is supplied.",
                "contract": {"parameters": self.parameters},
            }]},
        }


def candidate_only(domain_name, text, name, parameters):
    source_id = "documentation_fixture"
    observation = {
        "kind": "operation", "observation_id": "action_1",
        "source_action": name, "text": text,
        "evidence": [SourceSpan.locate(source_id, text, text).to_dict()],
    }
    domain = SimpleNamespace(
        name=domain_name, curation_policy=CurationPolicy(domain_name)
    )
    evolved, report = maintain_library(
        Registry(), [observation], sources={source_id: text},
        runner=RecordedCurator(name, parameters), domain=domain,
    )
    candidate = evolved.snapshot["operation_candidates"][0]
    assert candidate["status"] == "candidate_not_executable"
    assert name not in evolved.snapshot["operations"]
    return evolved, report


bio, bio_report = candidate_only(
    "biology.protocol/1", "Centrifuge at 5000 g for 5 min.",
    "Centrifuge", {"rcf_g": "relative_acceleration", "duration_s": "time"},
)
materials, materials_report = candidate_only(
    "materials.solids/1", "Anneal the sample under argon.",
    "Anneal", {"temperature_C": "temperature", "atmosphere": "gas_identity"},
)
```

该示意只把带精确引用的动作归入候选并保留领域标识。它不解析或补全数字；例如第二段没有温度和保温时长，合同中的参数名不会生成对应数值。`CurationPolicy(domain_name)` 没有注册宏实现，因此不会因为名称像某个已知操作而自动取得可执行资格。

后续真正接入完整转换时，需提供以下 implementation，而不是只修改 `domain` 字符串：

| 实际 seam | 生物领域 adapter 应处理的内容 | 材料领域 adapter 应处理的内容 |
| --- | --- | --- |
| `registry()` / `with_registry()` | 有领域作用范围的操作、样品和风险合同；不得把化学风险类别直接当生物风险全集 | 固体样品、相、气氛、升降温和测量合同；保留不同设备作用位置 |
| `extract(document, runner, ...)` | 只读原文，保留培养、移液、离心、洗涤、检测的顺序；不把相对离心力 `g` 当作 `rpm` | 保留研磨、压制、退火、烧结及表征；原文没有的升温速率、保温时间、气体流量保持未知 |
| `validate(extracted, raw, run_id)` | 对类型、维度、动作覆盖、物料与端点进行领域核查；原始参考字段只作独立对照 | 区分样品温度、炉温和程序设定；验证样品形态、气氛、热历史与端点；不从参考字段补值 |
| `curation_policy()` | 为确已实现的合同提供类型及状态 verifier；没有转子几何信息时，不能通过转换公式臆造 `g` / `rpm` 等价 | 为实际支持的分解提供 verifier；保温、热循环和气氛变化不能只因都涉及加热而合并 |
| `mutate(...)` | 使用生物领域的适用前提与错误机制；没有实现时明确不生成这一类 negative | 使用材料领域的热程序、样品和设备约束；不直接套用溶液反应的风险标签 |
| 导出与设备 adapter | LabOP 或特定液体处理平台可以是后续独立目标；每种操作必须有经过核查的 mapping | 若平台与标准不能表达目标操作，保留 IR 和未支持原因；不得生成看似标准的自造 XDL 标签 |

已有通用构建 interface 的接线形式如下；其中 `implemented_domain_adapter` **需要先实现、测试并固定版本**，本仓库没有提供名为该变量的生物或材料 adapter：

```python
from mosaic import BuildSpec, Runtime, build
from mosaic.sources import load_text_sources

adapter = implemented_domain_adapter
result = build(
    BuildSpec(domain=adapter.name, positives=1, per_risk=0),
    runtime=Runtime(
        records=load_text_sources(["procedures/domain_example.txt"]),
        domain=adapter,
    ),
)
```

LabOP 的 Protocol / Execution 分离及 `BehaviorSpecialization` 提供了表达与平台解释分开的实际参考，但不能据此认定本项目已能转换任何 LabOP primitive。[LabOP 作者文档](https://github.com/Bioprotocols/labop/tree/develop) 对 Opentrons 的适配仍需要明确的容器定义、模块与夹具组合；“有标准孔板”不能省略几何与交互检查。[Opentrons 官方定义说明](https://docs.opentrons.com/flex/labware/definitions/) XDL 中已有 HeatChill 也不能自动证明烧结、退火或生物培养已得到语义完整的表示及物理执行支持。[XDL 官方操作规范](https://croningroup.gitlab.io/chemputer/xdl/standard/full_steps_specification.html)

## 验收重点

应以混入矛盾 ORD 字段仍保持文本结果、短流程和无 ORD 的文本文件可提取、原文后处理动作不丢失、器材同族但条件不兼容/未知、实际库 revision 变化且可重放、至少两个领域合同在同一 interface 下工作为验证对象。跨领域样例必须明确标注测试合同或真实来源，不能仅换领域名称就宣称支持。
