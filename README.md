# MOSAIC

MOSAIC 将**实验流程纯文本转换为有来源证据的规范 XDL**。当前仓库专注迭代这套智能体，不再包含风险负例基准、模型训练、ORD 下载、SOP 补样或官方平台编译工具。

## 使用

Python 3.10+：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
./.venv/Scripts/python.exe -m pip install -e . --no-deps
./.venv/Scripts/python.exe -m mosaic api-check
./.venv/Scripts/python.exe -m mosaic extract examples/procedure.txt
```

在 `.env` 中填写 `api_key`、`base_url`、`model`，格式见 [.env.example](.env.example)。检查接口使用随机 nonce 和无效密钥对照；网关返回的模型名称不构成独立身份认证。密钥不写入转换记录。

输入必须显式提供，支持 `.txt`、`.md`、含 `procedure` 或 `text` 的 JSON 单记录／数组，以及 JSONL，也可提供目录。JSON 的其他结构字段不用于补全实验事实。例子是明确标注的演示文本，不计实验数据。

```powershell
./.venv/Scripts/python.exe -m mosaic extract path/to/procedures --output-dir outputs --workers 4 --max-calls 100
./.venv/Scripts/python.exe -m mosaic extract procedure.txt --registry outputs/mosaic_<hash>/library_registry.json
./.venv/Scripts/python.exe -m mosaic extract procedure.txt --model extractor=your-model --model critic=your-model
```

`--no-curation` 可暂不调用库维护角色。默认读取 `.env` 的模型，各角色也可用 `--model ROLE=MODEL` 单独配置。预算限制 completion 调用次数，HTTP 有有限重试。

## 智能体与确定性检查

| 角色 | 职责 |
|---|---|
| `extractor` | 提取动作、物料、参数和顺序，附逐字原文证据 |
| `critic` | 核对遗漏、虚构和顺序，提出有证据的修复 |
| `operation_expander` | 补充未表达动作；复用规范概念，必要时提出声明式操作合同 |
| `apparatus_mapper` | 识别来源器材、配置及适用范围，不猜型号或额定参数 |
| `library_curator` | 汇总观察，提出规范概念、别名、组合或器材分组修订 |

程序负责表述归一、单位转换、合同校验、来源检查、XDL 编解码和版本记录。未知表达不强配；缺失参数用 `__NOT_REPORTED__`，定性描述用 `__QUALITATIVE__`，歧义用 `__AMBIGUOUS__`，保留原文。操作表达、参数完整性和设备执行支持分别记录。

新操作与映射必须通过来源、合同及往返见证检查。器材目前自动登记观察、归入已有族或形成新族候选；新规范器材子型和替换规则仍需受控维护。最终 XDL 使用自描述的 `mosaic-canonical/1` 扩展，新增语义不自动获得 Chemputer 执行支持。

## 输出与重放

每次转换写入独立的 `outputs/mosaic_<hash>/`：

```text
manifest.json             # 固定输入、代码、库和模型配置的版本
records.jsonl             # 转换成功的完整记录
sources.jsonl             # 原始文本和来源快照
candidates.jsonl           # 工具未完成的转换，供核对
failures.jsonl             # 未完成原因
xdl/                      # 每条转换的 XDL 文件
artifacts/                # 模型、程序阶段及证据回执
atomic_operations.json    # 本次规范操作使用统计
equipment_inventory.json # 器材观察与能力要求
library_registry.json     # 可传入下一次转换的库快照
library_evolution.json    # 库维护建议与准入结果
```

```powershell
./.venv/Scripts/python.exe -m mosaic verify outputs/mosaic_<hash>
./.venv/Scripts/python.exe -m mosaic resume outputs/mosaic_<hash> --offline
./.venv/Scripts/python.exe scripts/verify_replay.py outputs/mosaic_<hash>
```

代码、来源、库或配置改变时，严格重放拒绝续跑，需要重新转换。离线重放使用冻结的模型回执，不等于重新推理。失败来源保留原文和原因，不以编造参数换取转换通过。

## 人工检查（可选）

[审核网页](audit/README.md) 专门检查转换结果：逐条翻页，对照原文、参数、器材与 XDL。网页只写 SQLite，显式导出时才合并审核结果；不与源 JSON 同步。

```powershell
./.venv/Scripts/python.exe -m mosaic publish outputs/mosaic_<hash> --db audit/data/reviews.sqlite3
./audit/start_review.ps1
```

## 结构与测试

```text
src/mosaic/          # 五个角色、编排、库演化、证据和持久化
  protocol/          # 文本参数解析、规范表示、器材归一和 XDL 编解码
libraries/           # 四份公共规范库及提取表示的内部定义
schemas/             # XDL 标准子集的内部校验
examples/            # 最小使用示例
scripts/             # 重放检查和转换启动脚本
tests/              # 仅覆盖当前转换、库维护和审核功能
audit/              # 可选的转换结果审核工具
docs/               # 当前架构和语言说明
```

```powershell
./.venv/Scripts/python.exe -m pytest -q
```

测试使用明确的模型替身，不依赖真实 API、旧数据集或官方平台 SDK。设计见 [架构](docs/ARCHITECTURE.md)、[规范词汇](docs/CANONICAL_VOCABULARY.md)及[扩展语言](docs/EXTENDED_XDL.md)。
