# 转换结果审核

本工具只服务 MOSAIC 的文本→XDL 结果检查。先导入转换记录，再从 SQLite 逐条审核；JSON 和数据库不自动同步。

## 启动

```powershell
python -m venv audit/.venv
./audit/.venv/Scripts/python.exe -m pip install -r audit/requirements.txt
./.venv/Scripts/python.exe -m mosaic publish outputs/mosaic_<hash> --db audit/data/reviews.sqlite3
./audit/start_review.ps1
```

打开 <http://localhost:8501>。也可以直接使用 `streamlit run audit/app.py`。侧边栏提供“新建数据库”和“打开现有数据库”，支持首次上传或按路径导入 JSON／JSONL。

当前数据库版本专用于转换结果；旧风险样例数据库不自动迁移或覆盖。更换数据库时选择新的文件路径。

## 审核

填写审核人，按上一条／下一条翻页。优先核对缺参提示、原文与步骤证据，再检查规范参数、器材子型及 XDL。通过、拒绝或撤销只更新 SQLite，带审核人、UTC 时间和操作历史；重复或过期页面提交会被拒绝。

通过表示专家认可当前转换表示，导出时将 quality.tier 写为 gold；不表示实验已经安全认证或机器可以执行。

## 独立导入／导出

```powershell
./.venv/Scripts/python.exe audit/import_json_to_db.py outputs/mosaic_<hash>/records.jsonl outputs/mosaic_<hash>/candidates.jsonl --db audit/data/reviews.sqlite3
./.venv/Scripts/python.exe audit/export_db_to_json.py --db audit/data/reviews.sqlite3 --status accepted --output audit/exports
```

导入按 ID 幂等，保留完整 JSON 和已有审核决定。MOSAIC 发布遇到同 ID 不同内容会拒绝整批导入。

导出支持单文件或按记录拆分，每次新建 UTC 时间戳目录。只增量合并审核元信息，使用临时文件加 os.replace 原子写入，并生成 CSV 汇总。网页也支持按当前筛选或全部记录导出。

依赖只有 streamlit、pandas；SQLite 使用 Python 标准库。审核存储与导入导出不依赖这两个界面包。
