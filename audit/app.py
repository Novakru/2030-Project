"""One-record-at-a-time review of MOSAIC text-to-XDL conversions."""
import json
import os
from pathlib import Path
import sqlite3
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import db
from audit.export_db_to_json import export_database
from audit.import_json_to_db import import_documents, import_paths
from audit.records import as_dict, field, protocol, quality, step_rows


LABELS = {"pending": "待审核", "accepted": "已通过", "rejected": "已拒绝", "reviewed": "已审核", "all": "全部"}


def main():
    st.set_page_config(page_title="MOSAIC 转换审核", layout="wide")
    if st.query_params.get("help") == "1":
        st.markdown((Path(__file__).parent / "HELP.md").read_text(encoding="utf-8"))
        st.link_button("返回审核", "?")
        return
    st.title("MOSAIC 转换审核")
    st.caption("逐条核对原文、规范操作、参数和器材，再判断 XDL 是否忠实表达。")
    with st.sidebar:
        st.link_button("使用帮助", "?help=1")
        reviewer = st.text_input("审核人", key="reviewer")
        requested = st.text_input("SQLite 路径", value=os.environ.get("MOSAIC_REVIEW_DB", str(db.DEFAULT_DB)))
        if st.button("打开现有数据库"):
            try:
                db.validate_database(requested)
                st.session_state.database = str(Path(requested).resolve())
                st.session_state.position = 0
                st.rerun()
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(str(error))
        if st.button("新建数据库"):
            try:
                st.session_state.database = str(db.init_database(requested))
                st.session_state.position = 0
                st.rerun()
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(str(error))
    database = st.session_state.get("database")
    if database is None and db.DEFAULT_DB.exists():
        try:
            db.validate_database(db.DEFAULT_DB)
            database = str(db.DEFAULT_DB)
            st.session_state.database = database
        except (ValueError, sqlite3.Error):
            pass
    if database is None:
        st.info("先在侧边栏打开或新建数据库，然后导入 MOSAIC 转换记录。")
        return
    try:
        db.validate_database(database)
        statistics = db.statistics(database)
    except (ValueError, OSError, sqlite3.Error) as error:
        st.error(str(error))
        return
    with st.sidebar:
        st.caption(database)
        reviewed = statistics["accepted"] + statistics["rejected"]
        st.progress(reviewed / statistics["total"] if statistics["total"] else 0,
                    text=f"已审核 {reviewed} / {statistics['total']}")
        status = st.selectbox("审核状态", ["pending", "all", "accepted", "rejected"], format_func=LABELS.get)
        search = st.text_input("查找记录 ID")
        with st.expander("首次导入 JSON / JSONL"):
            uploaded = st.file_uploader("上传转换记录", type=["json", "jsonl"], accept_multiple_files=True)
            source_path = st.text_input("或填写文件／目录路径")
            if st.button("导入数据库"):
                try:
                    if uploaded:
                        result = import_documents(database, [(item.name, item.getvalue().decode("utf-8-sig")) for item in uploaded], reject_changed=True)
                    elif source_path.strip():
                        result = import_paths(database, [source_path.strip()], reject_changed=True)
                    else:
                        raise ValueError("请选择 JSON/JSONL 文件或填写路径。")
                    st.success(f"导入 {result['inserted']} 条，跳过 {result['skipped']} 条")
                    st.session_state.position = 0
                except (ValueError, OSError, sqlite3.Error) as error:
                    st.error(str(error))
    filters = {"status": None if status == "all" else status, "search": search}
    rows = db.query_records(database, filters)
    if not rows:
        st.info("当前没有符合条件的记录。可导入 records.jsonl 和 candidates.jsonl，或切换审核状态。")
        return
    identity = (database, status, search)
    if st.session_state.get("queue") != identity:
        st.session_state.queue, st.session_state.position = identity, 0
    position = min(st.session_state.get("position", 0), len(rows) - 1)
    previous, counter, following = st.columns([1, 4, 1])
    if previous.button("上一条", disabled=position == 0, use_container_width=True):
        st.session_state.position = position - 1
        st.rerun()
    counter.markdown(f"**{position + 1} / {len(rows)}** · {rows[position]['record_id']}")
    if following.button("下一条", disabled=position == len(rows)-1, use_container_width=True):
        st.session_state.position = position + 1
        st.rerun()
    row = db.get_record(database, rows[position]["record_id"])
    record = json.loads(row["raw_json"])
    converted = protocol(record)
    q = quality(record)
    failure = as_dict(record.get("mosaic")).get("conversion_failure")
    if failure:
        st.error("转换尚未完成：" + str(as_dict(failure).get("error", failure)))
    gaps = q.get("missing_parameters", [])
    if gaps:
        st.warning(f"有 {len(gaps)} 项来源参数缺失、定性或存在歧义，请核对标识及原文。")
        with st.expander("定位缺参步骤", expanded=True):
            st.json(gaps)
    left, right = st.columns(2)
    with left:
        st.subheader("实验原文")
        source = field(record, "source_text", "")
        st.code(source or "记录未携带原文", language=None, wrap_lines=True)
        with st.expander("来源与提取记录"):
            st.json({key: converted.get(key) for key in ("source", "extraction", "mosaic")})
    with right:
        st.subheader("规范流程")
        st.dataframe(pd.DataFrame(step_rows(record)), hide_index=True, use_container_width=True)
        with st.expander("步骤参数与原文证据"):
            st.json(converted.get("steps", []))
        with st.expander("器材类别、子型与配置"):
            st.json(converted.get("hardware", {}))
        with st.expander("规范操作合同与表述映射"):
            st.json({key: converted.get(key) for key in ("operation_definitions", "normalization", "temporal_relations")})
    with st.expander("XDL 文件"):
        xml = field(record, "xdl", "")
        st.code(xml, language="xml")
        if xml:
            st.download_button("下载 XDL", xml, file_name=row["record_id"] + ".xdl", mime="application/xml")
    with st.expander("完整 JSON / 来源检查"):
        st.json(record)
    st.divider()
    if row["status"] != "pending":
        st.success(f"{LABELS[row['status']]} · {row['reviewer']} · {row['reviewed_at']}")
        st.write(row["comment"])
        if st.button("撤销审核", disabled=not reviewer.strip()):
            decide(database, row, "undo", reviewer, "")
    else:
        comment = st.text_input("审核意见（可选）", key="comment_" + row["record_id"])
        accept, reject = st.columns(2)
        if accept.button("通过 → gold", type="primary", disabled=not reviewer.strip(), use_container_width=True):
            decide(database, row, "accept", reviewer, comment)
        if reject.button("拒绝", disabled=not reviewer.strip(), use_container_width=True):
            decide(database, row, "reject", reviewer, comment)
    with st.expander("导出审核结果"):
        output = st.text_input("导出目录", value=str(Path(__file__).parent / "exports"))
        scope = st.radio("导出范围", ["当前筛选", "全部记录"], horizontal=True)
        mode = st.radio("文件组织", ["single", "split"], horizontal=True)
        if st.button("从数据库导出 JSON"):
            try:
                folder = export_database(database, output, mode, filters if scope == "当前筛选" else None)
                st.success(str(folder))
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(str(error))


def decide(database, row, decision, reviewer, comment):
    try:
        db.review_record(database, row["record_id"], decision, reviewer, comment, expected_revision=row["revision"])
        st.rerun()
    except (ValueError, sqlite3.Error) as error:
        st.error(str(error))


if __name__ == "__main__":
    main()
