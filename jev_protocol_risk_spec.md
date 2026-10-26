# 实验方案可行性判别数据集：构建规范 v0（化学 / XDL）

> 用途：交给 code agent 直接实施。只写“做什么、输入输出、验收标准”，不写背景论证。
> 风险分类饼图：`risk_taxonomy_pie.png`

---

## 0. 总体设计（一句话版）

正样本 = 从开源反应库抽取并经结构化字段交叉校验的 XDL；负样本 = 对正样本做**单故障注入**（每个负样本只含 1 个错误，便于归因）；判定分两路：
- **symbolic-jev**：A 器材 / B 物性安全 / D 流程逻辑 —— 硬规则，标签确定（0/1）。
- **jev（概率）**：C 化学条件 —— 软标签，用**真实失败数据**（HTE 低/零产率）校准，达标后才作为 Jev-as-judge。

优先级规则（保证不冗余）：一个扰动若同时命中 symbolic 规则与 C 类，**归入 symbolic 类**，C 类只保留规则无法判定的部分。

---

## 1. 数据源（按可用性排序）

| 源 | 用途 | 许可 | 备注 |
|---|---|---|---|
| ORD（`open-reaction-database/ord-data`，`ord-schema` 解析 .pb.gz） | 正样本主体：结构化条件（溶剂、温度、时间、气氛、用量）+ `notes.procedure_details` 文本 | 开放 | 大部分来自 USPTO |
| ORD 中的 HTE 数据集（Buchwald–Hartwig、Suzuki–Miyaura 等高通量筛选） | **C 类真实负样本**（产率≈0 的条件组合）与 jev 校准集 | 开放 | 这是唯一能“真实”证明条件错误的数据 |
| USPTO（Lowe 抽取，CC0） | 补充操作文本 | 开放 | 与 ORD 去重 |
| ORDerly | 已清洗的 ORD 条件数据、溶剂/试剂规范化映射 | 开放 | 直接复用其清洗规则 |
| PubChem（PUG-REST / PUG-View） | 沸点、熔点、闪点、自燃点、GHS 危害 | 开放 | B 类规则的物性来源 |
| CAMEO Chemicals / CRW（NOAA） | 反应性分组 + 两两不相容矩阵 | 免费 | B4 规则来源 |
| 厂商 datasheet | 器材参数 | — | A 类规则来源，每条记录附 `source_url` |
| Reaxys | 可选扩充 | **商业许可，通常禁止批量导出** | 无机构授权则不使用 |

可复用工具：
- 文本→动作序列：`rxn4chemistry/paragraph2actions`（开源；使用前核对模型许可）。
- 文本→ORD 结构：Ai et al. 2024（Digital Discovery，微调 LLM 抽取 ORD 结构）。
- XDL：Cronin 组 XDL 规范 / ChemIDE / SynthReader；CLAIRify（LLM 生成 XDL + 语法验证器迭代）的“生成-校验”循环思路。

---

## 2. 原子操作最小集合

### 2.1 捕获算法（可迁移到其他领域）
1. 词表并集：XDL steps ∪ paragraph2actions 动作类型（新领域则换成该领域的动作词表）。
2. 为每个操作写分解规则 `op → [primitive…]`；能被其他操作完全表示的标记为 **macro**。
3. **保留判据**：一个操作是 primitive，当且仅当它携带某个检查器需要、且其他操作无法携带的参数（温度、压力、波长、气体…）。
4. 在语料上验证：≥98% 的动作可映射到 primitive 或 macro；未覆盖动作写入 `unmapped.jsonl` 人工复核。
5. 输出 `primitives.yaml`、`macros.yaml`（分解规则）。

### 2.2 v0 结果（化学）

| Primitive | 必要参数 | 被哪些检查器使用 |
|---|---|---|
| `Add` | vessel, reagent, amount, rate?, T? | A1, B4, B5, C3, C4 |
| `Transfer` | from, to, volume | A1, A5 |
| `HeatChill` | vessel, T, duration?, ramp? | A2, B1–B3, C2 |
| `Stir` | vessel, rpm, duration? | A3 |
| `Wait` | duration | C6 |
| `Atmosphere` | vessel, gas, mode∈{purge, evac_refill, balloon} | C5 |
| `Separate` | vessel, keep_phase | A5, D1 |
| `Filter` | vessel, keep∈{solid, filtrate} | A5, D1 |
| `Evaporate` | vessel, P, T | A6→B1, A2 |
| `Irradiate` | λ, power, duration | A2（光源范围） |
| `Sonicate` | duration, power? | — |
| `Purify` | method（opaque，终端操作，不展开） | D1 |

Macro（存储时展开为 primitive，原名保留在 `meta.macro`）：Reflux、Quench、Extract、Wash、DrySolution、Recrystallize、Dissolve、AdjustPH、Concentrate、Triturate、Precipitate。

---

## 3. 正样本构建流水线

| 模块 | 输入 → 输出 | 验收 |
|---|---|---|
| P0 `ingest_ord` | ord-data → `reactions.parquet`（reaction SMILES、角色标注的组分、条件字段、procedure 文本、yield、dataset_id） | 字段解析无损；按 ORDerly 规则规范化溶剂/试剂名 |
| P1 `text2xdl` | procedure 文本 → XDL。主路径 paragraph2actions→规则转 XDL；失败回退 LLM 生成 + XDL 语法校验循环（≤3 轮） | XDL 通过 schema 校验 |
| P2 `crosscheck` | XDL 与 ORD 结构化字段比对：溶剂集合、温度（±5 °C）、时间、气氛、主要试剂当量（±10%） | 全部一致 → `gold`；部分一致 → `silver`（不进负样本生成）；冲突 → 丢弃 |
| P3 `bind_hardware` | gold XDL → 绑定到 `hardware_library` 中的一个默认装置配置（容器容量按总体积×1.5 向上取档） | 绑定后 symbolic-jev 全部规则通过（正样本必须 0 违规，否则丢弃） |
| P4 `dedup` | canonical XDL（排序参数、统一单位）SHA1 去重；同反应 SMILES 只保留 ≤3 个条件不同的方案 | 无重复 hash |

首批目标：gold 正样本 5k（USPTO 来源）+ HTE 全量。

---

## 4. 器材库 `hardware_library`（symbolic-jev 的事实基础）

Schema（每台设备一条）：
```yaml
id: hotplate_ika_rct_basic
category: heater_stirrer        # vessel | pump | valve | heater_stirrer | chiller | rotavap | separator | filter | light_source
params:
  T_min_C: ambient
  T_max_C: 310                  # 示例值，须按 datasheet 核对
  rpm_min: 50
  rpm_max: 1500
  max_vessel_mL: null
wetted_materials: [ ]           # pump/valve/管路必填：PTFE, PEEK, borosilicate, PFA, SS316…
ports: [ ]                      # 用于拓扑检查
source_url: <datasheet>
verified: false                 # 人工核对后置 true；仅 verified=true 的设备参与规则判定
```
首批范围：Chemputer 标准组件（注射泵、6 路阀、反应器、分液器、旋蒸、过滤器、冷却器）+ 每类 2–3 款常用商品设备。**只录入 datasheet 上能查到的参数，查不到即留空、不参与判定。**

---

## 5. 风险分类与负样本构造

记号：`label_type` = `hard`（规则确定）/ `soft`（概率）/ `real`（真实实验失败）。
每个子类给出：注入算子、前置条件（必须满足才注入）、判定依据。

### A 器材约束（symbolic-jev，hard）
| 子类 | 注入算子 | 前置条件 | 判定 |
|---|---|---|---|
| A1 容量/装填率越界 | 放大某 `Add/Transfer` 体积，或把容器换成小一档 | — | 累计体积 > 容器容量；加热/搅拌时装填率 > 2/3；单次 Transfer > 泵注射器容量且未分次 |
| A2 温控越界 | 把 `HeatChill.T` 设到设备范围外 | 设备 T 范围已 verified | T ∉ [T_min, T_max] |
| A3 转速/流速越界 | 改 rpm 或泵流速 | 同上 | 超设备范围 |
| A4 材质不兼容 | 引入与湿润部件不兼容的试剂（如 HF/强碱高温 vs 玻璃） | 设备 wetted_materials 已知 | 查材质兼容表 |
| A5 硬件拓扑缺件 | 删除某组件，或让步骤引用不连通的容器 | 有装置图 | 步骤所需组件不存在 / 图上无路径 |

### B 物性·安全临界（symbolic-jev，hard）
| 子类 | 注入算子 | 判定 |
|---|---|---|
| B1 开放体系超沸点 | 把 T 提到溶剂 bp+Δ（Δ∈{10,30,60} °C），且无回流/密闭标记 | T > bp(溶剂, 1 atm) 且体系开放；密闭但容器无耐压标记亦判错 |
| B2 低于凝固点 | 把低温步骤的溶剂换为 mp 高于目标 T 的溶剂（如 DMSO、水、苯在 −78 °C） | T < mp(溶剂混合物取最高组分) |
| B3 超闪点/自燃点 | 加热温度 ≥ 溶剂自燃点（如乙醚类），或明火/热板表面温度场景 | T ≥ AIT；或 T > 闪点且设备非防爆 |
| B4 不相容试剂对 | 把某试剂/溶剂替换成与体系中已有组分属于 CAMEO 不相容组的物质（遇水反应物 + 水/醇；氧化剂 + 还原剂；酸 + 氰化物/叠氮化物） | CAMEO 矩阵命中 “Hazardous”级 |
| B5 加料顺序放热 | 交换两步 `Add` 顺序（典型：水加入浓酸、淬灭顺序反转） | 顺序规则表（人工整理 ≤30 条，每条附文献） |

### C 化学条件（jev，soft / real）
| 子类 | 注入算子 | 前置条件 / 过滤 | 标签 |
|---|---|---|---|
| C1 溶剂错误 | 换成该反应类（按反应模板/名称反应分类）**从未出现**的溶剂，且极性/质子性类别不同 | 不命中 B4（否则归 B4） | soft：p = f(该溶剂在同类反应中的频次, 物性距离) |
| C2 温度偏移 | T 移到同类反应温度分布的 <1% 或 >99% 分位之外 | 不命中 A2/B1/B2 | soft：按分位距离映射 |
| C3 试剂/催化剂错误 | 替换碱/还原剂/配体/催化剂为同角色但同类反应未见的物质；或删除催化剂 | — | HTE 来源为 real；其余 soft |
| C4 计量错误 | 当量 ×0.1 / ×10，或限量试剂互换 | — | soft |
| C5 气氛缺失 | 删除 `Atmosphere`，体系含空气/水敏试剂（规则表：有机锂、格氏、Pd(0)、NaH…） | — | 体系含敏感试剂时为 hard，否则不注入 |
| C6 时间错误 | duration 缩到同类分布 <1% 分位 | — | soft |

C 类**假负样本过滤（必须）**：扰动后的（反应模板, 条件）若在 ORD 中以产率 ≥ 阈值（默认 30%）出现过 → 丢弃该负样本。

### D 流程逻辑（symbolic-jev，hard）
| 子类 | 注入算子 | 判定 |
|---|---|---|
| D1 步骤顺序错 | 交换有依赖的两步（如 Filter 在反应前、Evaporate 在 Extract 前） | 依赖图（数据流：产物所在容器/相）违背 |
| D2 关键步骤缺失 | 删除淬灭、干燥、相分离等 | 规则表：如 LiAlH4 后接水相操作前必须有 Quench |
| D3 引用未声明 | 引用不存在的试剂/容器 | XDL 静态检查 |
| D4 单位/数量级 | mL↔L、mg↔g | 由 A1 或 C4 实际判定；只保留无法被二者覆盖的情况 |

### 明确不做（无可靠数据或无法构造）
放热动力学/热失控定量、混合传质效率、光敏/热敏降解、杂质与副反应路径、器材老化故障、多故障组合（v1 之后再做）。

### 配比
见饼图：A 20% / B 22% / C 43% / D 15%。实际数量按“前置条件可满足的正样本数”截断，**不为凑比例放宽前置条件**；子类可用样本 < 200 时合并或砍掉，在报告中注明。

---

## 6. 样本 Schema

```json
{
  "id": "neg_000123",
  "parent_id": "pos_000045",
  "source": {"db": "ORD", "dataset_id": "...", "reaction_id": "..."},
  "reaction_smiles": "...",
  "xdl": "<XDL>...</XDL>",
  "hardware_config_id": "chemputer_default_v0",
  "label": {
    "feasible": false,
    "label_type": "hard | soft | real",
    "p_infeasible": 1.0,
    "risk_l1": "B",
    "risk_l2": "B1",
    "judge": "symbolic | jev",
    "evidence": {"rule_id": "B1.bp_open", "values": {"T": 95, "bp": 66, "solvent": "THF"}, "source_url": "..."}
  },
  "diff": [{"op": "replace", "path": "/steps/4/HeatChill/T", "from": 60, "to": 95}]
}
```
`diff` 必填：负样本必须能由 parent + diff 精确复原（保证单故障、可审计）。

---

## 7. jev 训练与 Jev-as-judge 准入

- 划分：按**反应模板 / 骨架**划分 train/val/test，禁止同一 parent 的正负样本跨集合。
- 训练目标：C 类用 soft label（BCE with soft target）；A/B/D 类不进 jev 训练（由 symbolic-jev 处理），或仅作辅助任务。
- 校准集：HTE `real` 样本（产率阈值：<5% 为失败，>30% 为成功，中间丢弃）。
- 准入标准（按 C 子类分别计算，任一不达标则该子类不作为 judge）：AUROC ≥ 0.80、ECE ≤ 0.05、在 HTE test 上 precision@p≥0.9 ≥ 0.85。
- 输出：`judge_report.md`（每子类指标、可靠性图、失败案例 20 条）。

---

## 8. 代码结构与交付物

```
src/
  ingest/ord_loader.py          # P0
  xdl/text2xdl.py  xdl/canon.py # P1, P4
  xdl/crosscheck.py             # P2
  hardware/library.yaml  hardware/bind.py   # §4, P3
  props/pubchem.py  props/cameo.py          # 物性与不相容矩阵（本地缓存）
  symbolic/rules/{A,B,D}*.py  symbolic/engine.py  # 每条规则 = 纯函数 (xdl, hw, props) -> Violation|None
  perturb/{A,B,C,D}*.py         # 每个子类一个算子：precondition() / apply() / label()
  perturb/fn_filter.py          # C 类假负样本过滤
  jev/train.py  jev/calibrate.py
data/  primitives.yaml  macros.yaml  rules_order.yaml(B5)  rules_required_steps.yaml(D2)
```
交付物：`positives.jsonl`、`negatives.jsonl`、`stats.md`（实际各子类数量 + 饼图重绘）、`judge_report.md`。

## 9. 测试（每个规则/算子必须有）
- 每条 symbolic 规则：≥3 个手写正例 + ≥3 个反例单元测试。
- 每个注入算子：属性测试——(1) 注入后恰好触发目标规则且**只**触发它；(2) parent 必须 0 违规。
- 端到端：随机抽 100 个负样本人工复核，hard 类错误率 < 2%，否则修规则后重跑。

## 10. 里程碑
1. P0–P4 + 器材库 20 台设备（verified） → 正样本 1k。
2. A/B/D 规则与算子 + 测试 → hard 负样本。
3. C 类算子 + 假负样本过滤 + HTE 抽取 → soft/real 负样本。
4. jev 训练、校准、准入报告。
