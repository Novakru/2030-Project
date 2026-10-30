# MOSAIC

MOSAIC 将实验流程原文转换为带来源证据的扩展 XDL。同一份 Facts IR 贯穿提取、核查、库映射和编译；不从 ORD 投料、条件、产率等结构字段补写原文。最终由专家审核。

## 使用

Python 3.10+：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[test]"
./.venv/Scripts/python.exe -m mosaic api-check
./.venv/Scripts/python.exe -m mosaic extract examples/procedure.txt
```

`requirements.lock.txt` 固定 Windows / Python 3.10 的依赖及轮子哈希。复现该环境时先安装锁文件，再执行 `pip install -e . --no-deps`。审核网页另用 [audit/requirements.txt](audit/requirements.txt)，仍只列 streamlit、pandas。

在 `.env` 填写 `api_key`、`base_url`、`model`，见 [.env.example](.env.example)。接口检查包含随机 nonce 和无效密钥对照；网关不能独立证明上游模型身份。密钥不写入回执。

输入支持 `.txt`、`.md`、JSON 单记录／数组及 JSONL。JSON 使用 `procedure`、`text` 或 `notes.procedure_details` 的逐字原文。目录应只包含流程文件；示例中的 README 和 selection.json 不是输入，请明确指定 sources.json。

```powershell
./.venv/Scripts/python.exe -m mosaic extract procedure.json --workers 3 --max-seconds 900
./.venv/Scripts/python.exe -m mosaic extract procedure.txt --registry outputs/mosaic_<hash>/library_registry.json
./.venv/Scripts/python.exe -m mosaic extract procedure.txt --model verifier=your-model
```

默认最多 `3 × 原文条数 + 2` 次模型请求：通常每条提取、核查各一次；格式与事实修复共享一次机会；整批库维护最多两次。`--max-calls` 可收紧预算，`--no-curation` 关闭模型库维护。每次 HTTP 请求最多两次传输尝试，与语义调用分开统计。墙钟预算在调用及重试前检查，HTTP 使用剩余时间限制超时。

## 流程

| 角色／程序 | 职责 |
|---|---|
| extractor | 提取实体、事件、独立事实、范围、关系及逐字证据，不受现有操作枚举限制 |
| verifier | 单独对照全文核查遗漏、虚构、绑定、范围及时序，输出定位问题 |
| repairer | 按合同错误或核查问题修复一次，不修改无关的已验证事实 |
| library_curator | 整批提出别名、规范操作／器材及条件替换建议 |
| 确定性程序 | 严格类型、证据定位、单位比较、精确映射、库事务、XDL 编译和独立读回评价 |

模型之间仍可能有相关错误，意见一致不能充当人工真值。局部修复未经再次独立核查的状态会保留。库准入只认可声明式表示，科学语义保持 silver，不安装设备执行器。

同一投料的 mg 与 mmol 不互相覆盖；设备容量与剂量分开；加热块设定值不能当作样品温度。缺参用 `__NOT_REPORTED__`，定性值用 `__QUALITATIVE__`，歧义用 `__AMBIGUOUS__`，不猜数值。新操作／器材先演化库，再绑定同一份事实，不重新提取来源。

XDL 使用普通 Synthesis／Hardware／Reagents／Parameters／Procedure 元素及属性。Mix 导出具体混合方式；已验证的同步加热和搅拌可降为原生 HeatChill。尚无规则的并发关系明确失败并保留事实，不串行化后冒充成功。规范 ID、聚类、合同及证据留在 JSON。

## 输出、评价与重放

每次转换写入独立的 `outputs/mosaic_<hash>/`：

```text
manifest.json             # 固定输入、源码／提示、库、模型、依赖版本、评价文件及预算
sources.jsonl             # 原文和出处
facts.jsonl               # 完成核查的事实；中途失败的事实见 artifacts/candidates
records.jsonl             # 通过表示及编译保真检查的 silver 记录
candidates.jsonl          # 工具未完成的记录、已有事实及失败原因
failures.jsonl            # 实际工具失败；原文缺参本身不算失败
evaluation.json           # 全部输入分母、错误、调用、token、HTTP 次数、耗时
xdl/<id>.xdl              # 常规 XDL
xdl/<id>.json             # 配套扩展声明、器材配置、位置绑定及观察信息
atomic_operations.json    # 操作库及观察事件次数
equipment_inventory.json # 器材库及观察实例次数
library_registry.json     # 下一批可继承的完整库版本
library_evolution.json    # 提案、准入、拒绝和证据
artifacts/                # 不可变阶段回执及哈希链
```

```powershell
./.venv/Scripts/python.exe -m mosaic verify outputs/mosaic_<hash>
./.venv/Scripts/python.exe -m mosaic evaluate outputs/mosaic_<hash>
./.venv/Scripts/python.exe -m mosaic evaluate outputs/mosaic_<hash> --reference evaluation/references/microreactor.draft.json
./.venv/Scripts/python.exe -m mosaic resume outputs/mosaic_<hash> --offline
./.venv/Scripts/python.exe scripts/verify_replay.py outputs/mosaic_<hash>
```

`verify` 独立读取实际 XML，核对事实、物料绑定、器材子型、配置和时序，也检测擅自新增的动作或数值；不只比较重新导出的字符串。`evaluate` 可加入同一来源的参考事实，报告 precision／recall、数量和绑定、关系及未知状态。局部草案不提供全局 precision 或 F1。

只有完整、带审核人／时间／接受决定的专家参考，以及操作 ID、器材子型参考，才能用于批量闸门。没有人工参考时准确率为空、批量闸门为 false。助手草案和模型核查不自动变 gold。格式见 [评价说明](evaluation/README.md)。

源码、提示、库、依赖版本、来源、评价参考或配置改变时严格续跑会拒绝。完成后的离线续跑读取同一冻结输出，不等于新推理。旧版非 Facts 目录可以直接读文件，不在新版中续跑。

[chemistry_pilot](examples/chemistry_pilot/README.md) 五条是开发／回归输入。[chemistry_holdout](examples/chemistry_holdout/README.md) 五条用于新数据组隔离的工程验证，尚无专家参考，也未证明原始专利彼此独立。

## 人工检查

[审核网页](audit/README.md) 逐条展示原文、全部独立用量、器材子型、模型问题及 XDL。首次导入后直接访问 SQLite，不同步 JSON。审核决定保留姓名、UTC 时间和撤销历史；导出时合并结果。

```powershell
./.venv/Scripts/python.exe -m pip install -r audit/requirements.txt
./.venv/Scripts/python.exe -m mosaic publish outputs/mosaic_<hash> --db audit/data/facts_review.sqlite3
$env:MOSAIC_REVIEW_DB = "audit/data/facts_review.sqlite3"
./.venv/Scripts/python.exe -m streamlit run audit/app.py
```

## 维护

`facts.py` 是事实合同；`fact_extraction.py` 管模型预算和修复；`fact_binding.py`、`fact_evolution.py` 管词汇；`fact_xdl.py` 编译；`evaluation.py` 读回及评分；`engine.py` 编排与冻结；`audit/` 仅做人工审核。旧核心提取／补全／多套 IR 适配代码及对应旧实现测试已删除。

```powershell
./.venv/Scripts/python.exe -m pytest -q
```

设计和限制见 [架构](docs/ARCHITECTURE.md)、[评价设计](docs/EXTRACTION_EVALUATION_DESIGN.md)、[一手组件调研](docs/research/EXTRACTION_COMPONENTS.md)。
