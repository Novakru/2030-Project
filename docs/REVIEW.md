# 人工核对入口

用户现已要求建立独立的人工审核网页工具，入口见 [audit/README.md](../audit/README.md)。该工具面向 pos/neg 记录的人工作业，SQLite 保存快照和决定，时间戳导出才合并人工元数据；不与 JSON 文件同步。当前数据库全部待审核，未生成任何虚构人工决定。

规范要求人工核对器材参数后才能标记 `verified=true`。当前 `libraries/hardware.yaml` 将来源核对与人工验证分开，全部保持 `verified=false`。模板组件没有容量、压力或材质事实，不能只因为具有 Chemputer 风格名称就填入假参数。

以后开始审核时，可运行 `protocol-risk prepare-review` 生成逐项材料，在 `data/reviews/hardware/`、`data/reviews/protocols/` 填写核对人、日期、来源及判定，再运行 build。已有记录不会被覆盖，器材参数、流程或未知约束变化会使旧审核失效。原始器材事实仍保留在 hardware.yaml，运行时 verified 由有效记录推导。

`reports/manual_review.csv` 是固定种子的 100 条待复核队列，包含 origin、risk 和 parent_id。只在实际完成复核后填写 reviewer、correct 与 notes。工具不会自动填“人工通过”，也不会用另一轮 LLM 代替人工复核。

这份探索性队列可以包含控制场景。完整验收的 hard 错误率门槛只统计实际有资格的 gold 父流程 hard 负例；控制场景、soft 猜测、重复复核行和无效样本 ID 不能凑满 100 条。至少 100 条有效 hard 复核且错误率 <2% 才通过该门槛。

原数据流水线的严格 gold 验收还需要独立核对主要用量、完整流程范围、必要操作、装置图及无法由已有物性判断的约束。新网页按用户要求在人工通过后导出 `quality.tier=gold` 和人工决定，但保留 blocker、unknowns、硬件及可行性原值；该数据审核等级不替代原流水线的严格验收，也没有自动接入 build 或训练集。负例通过表示标签与错误流程经人工确认，不表示流程可行。
