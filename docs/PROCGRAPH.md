# ProcGraph：自然语言 → 物料流操作图 → XDL

代码：`src/mosaic/pg/`；命令：`python -m mosaic.pg`（安装后 `mosaic-pg`）。与旧 Facts 主链路并存，互不依赖。

## 1. 为什么重做

旧链路 0/5 的直接原因有二：

1. **格式失败远多于语义失败。** 模型要逐字抄写证据、把数值写成十进制字符串，严格校验在 `1/2 hour`、`0°-5° C.`、`4-M`、重复 ID 上全部拒绝。
2. **没有角色和状态。** `participant_ids` 是平铺列表，"把溶液滴加到悬浮液"只能表达为一堆物料同时加入，编译成两次 Add。

新设计把**能确定的交给程序，只把理解交给模型**。

## 2. 数据表示（`mosaic.procgraph/1`）

| 对象 | 含义 |
|---|---|
| `materials` | 化学实体（试剂、溶剂、气体、干燥剂、产物），按原文命名 |
| `equipment` | 容器/仪器/工具，`props` 绑定容量等数量 |
| `steps` | 操作。`target` = 被作用/接收的对象；`inputs` = 加入物及用量；`params` = 条件；`outputs` = 产生的新状态（`solid`/`filtrate`/`organic`…） |
| `products` / `observations` / `unbound` | 产物与收率；观察；不属于流程的数量及理由 |

`target` 和 `inputs` 可以引用物料，也可以引用**前面步骤产生的状态 ID**。这些引用本身就是反应图：

```
A 的溶液滴加到 C、D 在甲苯中的悬浮液
t1 prepare(described) A + THF        -> x1
t2 prepare(described) C + D + 甲苯   -> x2
t3 add target=x2 inputs=[x1]         -> x3   # x1、x2 必须先存在
```

`origin=described` 表示原文只描述了混合物、没写制备动作；`origin=action` 表示原文写了制备。不会补造原文没有的条件、顺序或容器。

**数量由程序拥有。** 预处理把每个"数字+单位"识别为 `«Q3|25.4 g»`（含区间、分数、负温度、`4-M`、`ten minutes`、`3 x`、比例；跳过 NMR/MS 表征），模型只引用 `Q3`。每个 Q 必须恰好绑定一处或放入 `unbound`，这是程序可检查的完整性约束。

操作库 `ops.yaml` 为每个操作定义角色合同（target/inputs 是否必需、允许的输出、常用参数、XDL 映射）。它同时用于提示词生成、校验、编译和库维护。

## 3. 多智能体流程

```
预处理(程序) → 提取 agent → 规整+自动修复(程序) → 校验(程序)
   → [修复 agent，仅在有错误时，≤2 轮] → [审查 agent] → [修复 agent]
   → 编译(程序)：XDL / 线性流程 / Mermaid / ORD 式汇总 / 任务视图
```

- **规整与自动修复**（不消耗模型调用）：包装层、字段别名、名字代替 ID、字面数量映射回 Q、动词形态（stirring→stir）、重复 ID、状态先用后产（稳定拓扑重排）、给 stir/heat 加了 inputs（拆成 add+stir）、设备误作 inputs、温度/时长参数名错位、原文中出现但未声明的物料。每次修改都记录在 `coercions`。
- **校验**只报告必须由模型理解才能修的问题，带定位：`E_REF`、`E_USE_BEFORE_DEF`、`E_ROLE_TARGET`、`E_CYCLE`、`E_Q_UNBOUND`、`E_Q_KIND`、`E_Q_DUP` 等。
- **审查 agent**专查角色反转、复合物、共指、数量归属、遗漏与虚构；只把 critical/major 交给修复。
- **修复结果只在不变差时采纳**，坏修复不会毁掉好结果。
- **状态分级**：`ok`；`incomplete`（只剩数量放置类问题，图可用）；`has_errors`（结构问题）。任何情况下都会保存图并尽量编译。
- **规模化**：多线程批处理、断点续跑、按提示内容寻址的缓存、`--mode replay` 离线重放、长文本分窗提取并携带前文状态、`--samples k` 自一致性择优、批末库维护（`curate`，模型提议、程序把关、写入 `ops.local.yaml`）。

## 4. 输出

`outputs/<run>/`：`graphs/<id>.json`（图、错误、审查意见、自动修复日志、调用轨迹）、`xdl/<id>.xdl`、`views/<id>.md`（执行顺序流程 + Mermaid）、`tasks/<id>.json`（ORD 式分阶段汇总、依赖边、传递先后关系、可并行层级、数量槽位）、`summary.json`。

XDL 中，纯物料组成的 prepare 提到 `<Prep>`，复合物在独立容器配好后用 `Transfer` 转入接收容器；其余步骤按拓扑序单调分配到 Reaction/Workup/Purification。区间、定性条件与出处写为 XML 注释，不发明属性。

## 5. 评价

`evaluation/procgraph_gold/`：10 条 ORD 原文 + 4 组最小对照句的参考图（**助手起草，需专家审核**，状态 `assistant_draft_needs_expert_review`）。参考图由 `build_gold.py` 生成，并且必须通过正式校验器。

| 指标 | 含义 |
|---|---|
| material_f1 | 物料识别 |
| step_f1 / op_acc | 操作识别 / 操作标签 |
| qty_binding（严格/宽松）/ qty_coverage | 数量挂在正确物料或参数上 / 正确步骤上 / 被绑定比例 |
| role_acc | 接收物与加入物是否正确 |
| flow_f1 | 物料流边（反应图本身） |
| order_f1 | 图蕴含的先后关系（如"B 先配好再加 A"），召回按全部参考对计算 |

Q 编号由程序生成，预测与参考按字符区间对齐，所以数量绑定可以精确评分。

## 6. 使用

```powershell
copy .env.example .env    # 填 api_key；base_url=https://endpoint.greatrouter.com/v1；model=gpt-6.1-sol
python -m mosaic.pg ping
python -m mosaic.pg bench --gold evaluation/procgraph_gold --out outputs/pg_bench   # 报告：bench.md
python -m mosaic.pg extract examples/chemistry_holdout/sources.json --out outputs/pg_run
python -m mosaic.pg curate outputs/pg_run      # 未知操作 → 库维护
python -m mosaic.pg tasks  outputs/pg_run      # 生成带标签的任务样本
python -m mosaic.pg prepare examples/procedure.txt   # 查看标注后的输入
```

常用参数：`--no-critic`（省调用）、`--repair-rounds N`、`--samples k`、`--effort low|medium|high`、`--api responses|chat`、`--mode replay`、`--max-calls N`、`--workers N`。默认 API 先走 Responses（`/v1/responses`，带 `reasoning.effort`），网关不支持时自动退回 chat/completions；JSON 模式或 reasoning 参数被拒绝时自动去掉重试。

## 7. 测试

`pytest` 默认只跑新链路的 44 项测试（约 2 秒）：数量识别疑难写法、规整与自动修复、校验定位、最小对照句的顺序语义、XDL 构建顺序、评价器灵敏度、修复循环（含拒绝变差修复）、分窗、批处理续跑、库维护把关、Responses/chat 客户端回退与重试，以及 420 条随机损坏回复的模糊测试。旧链路测试移至 `tests/legacy/`，用 `pytest tests/legacy` 运行。

## 8. 已知限制

- 真实模型的基准分数需要在可访问网关的环境运行 `bench` 获得；本包中的测试都是离线的。
- 参考图只有 14 条，且未经专家审核，只能用于开发回归，不能证明批量泛化。
- 并发（`concurrent_with`）与循环只做了表示和校验，XDL 中没有原生并发编译。
