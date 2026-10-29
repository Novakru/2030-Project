# 反应流程人工审核工具

独立于提取和编译流水线的 Streamlit 小工具，供人工审核 pos、neg 或其他反应记录。Python 3.9+，建议 3.10+；运行依赖只有 `streamlit`、`pandas`，SQLite 使用标准库。

**数据边界：初始 JSON/JSONL → 显式导入 SQLite → 人工审核 → 显式导出新的 JSON。没有文件同步，不回写来源文件。**

## 快速启动

以下命令在项目根目录执行，PowerShell：

```powershell
python -m venv audit/.venv
./audit/.venv/Scripts/python.exe -m pip install -r audit/requirements.txt
./audit/start_review.ps1
```

打开 <http://localhost:8501> 后，已有默认数据库会自动连接，直接进入逐条批改。优先使用 `audit/data/extended_reviews.sqlite3`，否则依次尝试旧 `text_reviews.sqlite3`、`mosaic.sqlite3` 和 `reviews.sqlite3`。也可在侧边栏打开其他库或首次导入。当前数量以数据库进度和 `data/mosaic/current.json` 指向的清单为准。启动脚本默认监听本机；端口占用时可指定 `./audit/start_review.ps1 -Port 8502`。

每条记录保存完整 `source_text`，在「对照实验原文」展开查看，不依赖来源 JSON 继续存在。`reference_metadata` 的 ORD 注释仅供比较。扩展批次的新动作有 `operation_definitions`，原文缺参采用显式标识；动作表达完整的记录可计入正例。`extraction_candidates.jsonl` 仅保存工具未完成的格式、证据或动作覆盖问题，识别为「其他记录」，供专家检查。

当前扩展批次已导入 120 条 pos、85 条 neg 和 100 条工具未完成记录，共 305 条待审。98 条 pos 含原文缺参标记；「核对位置」可选择扩展操作合同或来源参数，直接定位相关步骤。表达完整不代表参数齐全或设备执行已验证；旧数据库另存，不与本批同步。

侧边栏「使用帮助」会在新标签页打开基本操作说明，也可直接访问 <http://localhost:8501/?help=1>。关闭帮助页即可回到原审核位置。

也可直接运行，Linux/macOS 使用相应的 Python 路径：

```powershell
./audit/.venv/Scripts/python.exe -m streamlit run audit/app.py --server.address 127.0.0.1
```

可通过 `start_review.ps1 -Database "D:/reviews/team.sqlite3"` 或环境变量 `AUDIT_DB` 设置侧边栏的默认数据库路径。直接启动时界面沿用 Streamlit 主题，启动脚本使用浅色主题。

## 文件与存储

```text
audit/
  app.py                  # 网页：连接、队列、详情、判定、导出、补充导入
  db.py                   # SQLite 表结构、查询、版本检查、审核历史
  records.py              # 平铺 / protocol 包装结构的字段适配
  review_view.py          # 从已有改动、证据、未知项生成核对点与步骤定位
  risk_reason.py          # 用现存规则证据解释风险原因，保留来源与适用条件
  import_json_to_db.py     # 独立导入；无需安装 Streamlit
  export_db_to_json.py     # 独立导出；无需安装 Streamlit
  start_review.ps1         # Windows 启动入口
  requirements.txt        # 仅 streamlit、pandas
  tests/                  # 后端与 Streamlit AppTest
  data/extended_reviews.sqlite3 # 扩展批次默认库，含审核状态，不纳入版本控制
  exports/review_<UTC>/   # 每次导出一个新目录，不纳入版本控制
  verification.json      # 本次实际数据与测试的交付验证记录
  README.md
  HELP.md                  # 网页帮助：基本审核、翻页、撤销和导入导出
```

数据库是长期保存的工作文件，不要在审核中删除或重新生成。运行中的 SQLite 可能带 `-wal`、`-shm` 文件；需要备份时先停止服务并关闭连接再复制，或使用标准库 `sqlite3.Connection.backup()` 生成一致性备份。多个审核人可通过同一个正在运行的 Streamlit 服务使用同一数据库。

## 第一次导入与后续打开

网页侧边栏选择「首次建库并导入」，填写数据库保存路径，然后选择数据路径或上传文件。上传文件时只导入上传内容；未上传时读取文本框中的路径，每行一个。导入成功后自动进入审核队列。后续访问只需「打开已有数据库」，无需原始 JSON 再次存在。

独立脚本的等效用法：

```powershell
python -m mosaic publish data/mosaic/mosaic_<批次哈希> --db audit/data/extended_reviews.sqlite3
python audit/import_json_to_db.py "D:/records" --db "D:/reviews/new.sqlite3"
```

支持单记录 JSON、JSON 数组、JSONL 和目录递归扫描；必须有顶层非空字符串 `id`。字段不要求与本项目完全相同。导入整批使用事务，解析或记录验证失败则整批记录回滚，不会只导入前半部分。新建数据库的空表结构可能保留，便于修正后重试。不要选择整个项目根目录，否则其中不含记录 ID 的配置 JSON 会触发验证失败；也不要选择含 `manifest.json` 的导出目录，单独导入 `records.json` 即可。

`raw_json` 保存每条原始对象的全部内容，空白格式规范化；列表顺序、未知字段和嵌套对象都保留。已有 ID 永不覆盖原始快照、索引类型或审核状态。输入变化的同 ID 会列入 `changed_duplicates`，不是静默更新；审核新版本时另建数据库。文件名不会自动变成记录 ID。

「数据管理」可显式补充导入。当前纯文本批次发布 `positives.jsonl`、`negatives.jsonl` 和 `extraction_candidates.jsonl`，最后一类明确不计正例。SOP／作者 XDL 仅在构建时显式启用后才会另计加入。界面只在 SQLite 查找父记录，不根据 `parent_id`、`xdl_path` 等字段读取磁盘文件。首次导入框默认列出当前清单的记录文件，不扫描整个批次目录。

记录类型默认从明确的 `record_type` / `kind`、`pos_` / `neg_` ID、风险标签及 `parent_id` 推断；无法判定的标记为「其他记录」。对外部命名的数据可用网页「本批记录类型」或 CLI `--kind positive|negative|other` 显式指定，原始 JSON 的标签不被改写。

## 审核流程

1. 在侧边栏填写审核人姓名。姓名是操作归属记录，不提供账号登录或身份认证。
2. 侧边栏选择本轮范围：默认待审核，可按 pos/neg 和风险筛选。层级、blockers、symbolic violations 和 ID 搜索收在「更多筛选」中。
3. 每页只展示一条。顶部「上一条 / 下一条」翻页，「跳转与刷新」可直接跳到本轮序号。单纯翻页不提交任何决定。
4. 默认定位本条的语义改动、核对冲突、未独立核对的用量或未知约束。左侧标亮相关步骤，右侧并排展示父记录／原文用量与当前值、已有风险证据及来源。多个核对点可用「核对位置」切换。
5. 可选填写意见，点击「通过并下一条」或「拒绝并下一条」。决定只写 SQLite，并自动跳到本轮后续待审记录；到末尾时停留并提示。负例通过后仍保留负例标签。
6. 本轮固定记录顺序，提交后仍能用「上一条」回看已审记录。已审记录显示决定、审核人、UTC 时间和意见；需要纠正时先点「撤销审核」。「刷新本轮队列」会重新应用筛选条件。

首屏只呈现本次核对所需内容。相邻步骤、完整流程和「完整证据与其他资料」按需展开；完整 crosscheck、quality、reagents、器材、XDL、原始 JSON、父记录及审核历史仍可查看。B5／D1 的相邻步骤默认展开，便于核对顺序；被删除步骤有父记录时单独显示原步骤，原生 XDL 按 contract 的 XPath 定位到后续使用物料的步骤。

定位器只整理已有字段，**不会新增风险判定**，也不会把未匹配的用量或未知约束判成错误。父记录未入库时原值明确显示未知；用量对照保留数值和单位。索引、质量状态和 XDL 重新序列化等附带变化收在完整记录中，主视图优先展示 steps / reagents / hardware / context 的改动。

负例右侧显示「风险原因（原标注）」：优先展示已有 `label.reason` / `rationale`；没有文字原因时，用原 `label.evidence` 中的 `rule_id`、`values`，或原生 XDL `contract` 整理说明。保留原数值，即使与规则不一致也不篡改为一致。默认显示触发条件，「核对规则与适用条件」可查看点火源、纯溶剂等上下文、原判定器和适用范围；完整资料保留原始证据及解释来源。soft 明确标为条件扰动假设，不等于观测失败；未知规则或缺少原因时明确提示，不自动编造。解释仅在界面展示，不写入原 JSON、数据库标签或审核决定。

A5 缺少控制器时，优先定位明确的加热步骤，显示缺失设备、具体温度和时长，并解释保留绑定为何仍是悬空引用；父记录未导入时不推断删除历史。设备对照以名称和库 ID 显示，完整配置仍保留在原始资料中。「核对规则与适用条件」同时列出其他受影响步骤及统一绑定搅拌／控温设备的建模假设。

**pos/neg 是样本性质，accept/reject 是数据审核决定。** 对 neg 点击通过，是确认它的错误流程、风险标注和证据匹配；它仍然是负例，`label.feasible=false`、`audit`、`diff`、`mutation` 等原样保留。不会修复负例流程，也不把负例改为可行正例。

完整资料中的「导入层级」是原始 tier，「当前层级」随决定变化；通过显示 gold，待审核或拒绝显示原层级。风险筛选取自 `label.risk_l2`、`audit.child_risks`、`mutation.risk`，缺失风险标签不会从步骤猜测。用量、容量按记录展示，不做密度换算或未经支持的累计体积推算。

该工具按本次要求提供简单的人工判定出口。**人工数据审核通过与完整平台可执行性、硬件验证是不同事实**：不会清空 gold blockers、unknown constraints，或自动设置 hardware verified、full_feasibility_certified。原有严格 gold 验收规则和构建流水线没有接入本数据库；本工具导出也不会自动进入训练集或覆盖数据集文件。

## 导出与时间戳

侧边栏进入「导出」页，可选「当前筛选结果」或「全部记录」，配置服务器导出父目录，选择单 JSON 数组或拆分记录。导出按数据库当前状态应用侧边栏条件；例如筛选「待审核」时，不包括本轮为回看而保留的已审记录。点击「生成时间戳导出」后还可下载 JSON 数组和 CSV；下载内容是该次导出快照，后续决定改变时需重新导出。

```powershell
# 全部记录，单个 JSON 数组 + CSV
python audit/export_db_to_json.py --db audit/data/reviews.sqlite3 --output audit/exports
# 已通过负例 A1，每条一份 JSON
python audit/export_db_to_json.py --status accepted --kind negative --risk A1 --mode split
# 所有已审核记录（通过和拒绝）
python audit/export_db_to_json.py --status reviewed
# 其他可组合筛选
python audit/export_db_to_json.py --status pending --tier silver --blockers yes --symbolic no --search pos_
```

输出示例：`audit/exports/review_20261026T070000_123456Z/records.json`。微秒 UTC 时间戳区分每次导出，不覆盖上次结果；拆分模式使用安全 ID 文件名与哈希后缀，记录 ID 不能跳出输出目录。每个文件都先写同目录临时文件、flush/fsync，再 `os.replace`。多文件导出以最后写入的 `manifest.json` 且 `complete=true` 标志完成；没有该标志的目录是中断的导出，不应作为完整批次使用。失败的导出目录会保留，便于排查。

JSON 合并规则：

- 待审核：完整保留原始对象。
- 通过：设置 `quality.tier="gold"`，写入 `quality.manual_review={reviewer, reviewed_at, decision:"accept", comment}`。
- 拒绝：写入相同人工字段且 `decision="reject"`，保留导入层级（silver 保持 silver；当前负例的 perturbed 也保持 perturbed）。
- 已有顶层 `quality` 时在顶层更新；只有 `protocol.quality` 时在原有嵌套位置更新；没有 quality 时新增顶层 quality。其余所有字段保持原值，包括 `crosscheck.tier` 和风险标注。
- CSV 包含原层级、当前层级、审核状态、审核人、时间、意见、来源和修订号；可能被表格软件当成公式的文本添加前导单引号，JSON 原始值不受影响。

## 数据库结构与多人操作

`records` 以 `record_id` 为主键，含完整 `raw_json`、规范化 SHA256、`tier`、`record_type`、`parent_id`、blockers/violations 索引、`status`、`reviewer`、`reviewed_at`、`comment`、导入来源与时间、`revision`。`record_risks` 提供风险筛选，`review_events` 追加保存每次通过、拒绝和撤销以及上一决定。

状态为 `pending / accepted / rejected`。决定与历史在同一个事务里提交；版本号检查和 SQLite 写锁保证两个审核人不能覆盖彼此的已提交决定。撤销同样要求当前版本，防止旧页面撤销较新的判定。Web 未提供记录删除或原始 JSON 编辑，以保留可追溯性。

## 验证

```powershell
./audit/.venv/Scripts/python.exe -m unittest discover -s audit/tests -v
```

测试仅操作临时数据库和夹具，不审核真实样本；包含解析与回滚、幂等保护、嵌套负例导出、增量字段保持、两人争用、撤销历史、路径保护、原子写入失败，以及首次导入/已有库/翻页/自动下一条/返回撤销/刷新队列/导出的 Streamlit 交互。定位测试检查用量单位、父值保持、删步、原生 XDL 和过期原文别名。界面测试使用 Streamlit 自带的 AppTest，无额外测试依赖。

Streamlit 接口参考：[可选择的表格](https://docs.streamlit.io/develop/api-reference/data/st.dataframe)、[表单](https://docs.streamlit.io/develop/api-reference/execution-flow/st.form)、[AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)。
