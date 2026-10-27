# MOSAIC

**Multi-agent Orchestration for Source-grounded Actions, Instruments and Constraints**：从真实来源提取流程、映射器材、构造可重放的风险扰动，并把冻结批次送入人工审核。工作分支 `refactor/mosaic` 从 `main@7a960ed` 创建。

设计目标见 [docs/MOSAIC.md](docs/MOSAIC.md)，ACRA 论文与固定版本代码研究见 [docs/research/acra.md](docs/research/acra.md)。来源事实、建议配置、模型假设和人工决定分别保存；候选不自动成为经过实验认证的 gold。

当前交付：140 条 ORD raw／XDL、26 条补充父记录、200 条风险候选（20 类各 10 条，44 个扰动分组）。网页已导入 366 条待审记录，实测与仍需迭代的类别见 [质量报告](reports/mosaic_quality.md)。

## 安装与运行

Python 3.10+，在项目根目录执行：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
$env:PYTHONPATH = "$PWD/src"
$env:PYTHONIOENCODING = 'utf-8'
./.venv/Scripts/python.exe -m protocol_risk api-check
./.venv/Scripts/python.exe -m mosaic run --positives 140 --per-risk 10 --text-limit 60 --llm-perturbations 6 --max-calls 200 --workers 4 --model extractor=gpt-6.1-sol --model critic=gpt-6.1-sol
```

`.env` 提供 `api_key`、`base_url`、`model`，格式见 [.env.example](.env.example)。默认角色使用配置模型；`--model ROLE=MODEL` 可指定 `extractor`、`critic`、`apparatus_mapper`、`perturber`。连通性检查包含真实 nonce 请求和随机无效密钥对照，见 `reports/api_connectivity.json`；网关返回名称不是独立模型身份认证。

`--max-calls` 限制 completion 调用次数，HTTP 仍有有限重试；`--workers` 控制文字来源并发数，默认 4。失败调用和缓存重放独立记录。校验失败来源进入 `quarantined.jsonl`；数量或覆盖不足时批次为 `partial`。

来源位于 `data/raw/reactions.parquet`、`data/upstream/` 及相应锁文件。缺少 ORD 文件时先运行 `python -m protocol_risk fetch`、`python -m protocol_risk ingest`；作者 XDL 可用 `collect-chemputer` 恢复。SOP 使用锁文件中已下载并验证的来源，不可获取的候选不参与构造。

## 检查、重放和审核

`data/mosaic/current.json` 指向最新批次。下面的 `<run_dir>` 为 `data/mosaic/mosaic_…`：

```powershell
./.venv/Scripts/python.exe -m mosaic verify <run_dir>
./.venv/Scripts/python.exe -m mosaic resume <run_dir> --offline
./.venv/Scripts/python.exe -m mosaic publish <run_dir> --db audit/data/mosaic.sqlite3
./audit/start_review.ps1
```

`verify` 核对产物、上游 ORD、产率、器材引用、父子补丁、单次语义修改及目标风险；`--artifacts-only` 只核对冻结产物。`resume --offline` 重用保存的模型和程序阶段，不访问模型；代码、来源或库变化时拒绝续跑，应重新 `run`。离线重放不等于从空缓存重新推理。

打开 <http://localhost:8501> 逐条审核。首次导入可用网页上传或路径输入，随后只需打开 SQLite。发布不创建人工决定，也不覆盖已有 ID 或审核状态。JSON 与数据库不自动同步。审核后 JSON 由导出功能统一生成，每次使用独立时间戳目录。详见 [audit/README.md](audit/README.md)。

## 文件与职责

```text
src/mosaic/              # 唯一的数据集编排入口
  engine.py              # build / resume、选择来源、领域适配
  agents.py              # 有界角色调用、模型配置、重放记录
  chemistry.py           # 提取、批评、器材映射、领域校验
  evidence.py            # 原文定位、逐字引文、内容哈希
  registry.py            # 库版本、观察、候选操作、无损别名、覆盖求解
  catalog.py             # 器材和原子操作统计与最小集证据
  mutations.py           # 程序／模型扰动、语义约束、机制选择
  supplements.py         # SOP 片段、条件场景、原生 XDL 依赖契约
  verification.py        # 来源与扰动重放检查
  store.py               # 原子写入、不可变阶段产物、哈希链
  audit_bridge.py        # 冻结批次 → SQLite，显式单向发布
src/protocol_risk/       # 化学规则、来源解析器和获取工具
libraries/
  hardware.yaml          # 器材库
  primitives.yaml        # 独立原子操作库，含状态作用与风险语义
  risks.yaml             # 独立风险类别库
  macros.yaml            # 尚待证明无损的宏候选
audit/                   # 独立 Streamlit / pandas / sqlite3 审核工具
tests/                   # 行为与真实批次验收
data/
  raw/                   # 规范化 ORD 来源归档
  upstream/              # 锁定原始资料
  mosaic/
    current.json
    mosaic_<hash>/
      manifest.json      # 本批次唯一清单
      artifacts/         # 来源、模型响应、提取、校验、库维护
      datasets/<hash>/
        raw.jsonl
        positives.jsonl
        negatives.jsonl
        quarantined.jsonl
        xdl/             # 逐条 XDL
        atomic_operations.json
        equipment_inventory.json
```

文本提取不要求 ORD 已给出加料顺序；结构化重建要求明确顺序和可用单位。批评角色只能提出带原文证据的修复，程序决定是否接受。microreactor、孔板单孔容量、来源加热块保留适用范围，未知额定参数继续为未知。

领域可通过 `Runtime(domain=…, records=…)` 注入：领域负责提取、验证、扰动、库和来源，核心负责版本与持久化。当前以批式化学为主；光化学扩展示例要求来源中实际存在 `Irradiate`，流动、电化学、微波和动态条件仍需独立适配。

库维护自动登记有引文的器材观察和未映射动作候选；需先检查现有原语能否表达，候选不自动成为可执行原语。未知型号不自动合并，操作别名要求完整契约一致。最小覆盖只针对有证据的需求矩阵；缺少额定范围时报告未覆盖，不宣称已得到通用最小器材集或原子操作集。

扰动先检查前置条件，再校验实际修改。改多个步骤、修改器材额定参数或篡改来源均被拒绝。机制由真实修改和规则确定，数值变化不能自报新机制。soft 保留未校准假设；B2/B3 条件场景、B5 原文片段和原生 D2 单输入依赖分别统计，不能当作独立 ORD 失败实验。

旧全局 `build`、批量 `extract`、`build-sop` 等入口及旧派生数据已移除。官方平台编译兼容性暂不纳入主流程；静态 XDL 导出和真实设备执行是不同验收。

## 测试

```powershell
./.venv/Scripts/python.exe -m pytest -q
./audit/.venv/Scripts/python.exe -m unittest discover -s audit/tests -q
```

真实批次验收读取当前清单；手写控制只在 `tests/chemistry_fixtures.py` 作夹具，不计入交付数量。
