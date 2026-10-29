"""Streamlit UI. Original JSON is accessed only by the explicit import form."""
import hashlib
from html import escape
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import streamlit as st

from audit import db
from audit.export_db_to_json import DEFAULT_EXPORT, csv_bytes, export_rows, json_bytes, timestamp
from audit.import_json_to_db import import_documents, import_paths
from audit.records import as_dict, field, quality, step_rows
from audit.risk_reason import explain_risk
from audit.review_view import (FIELD_NAMES, focus_indices, procedure, review_points,
                               mechanism_name, risk_name, step_summary, text)

ROOT = Path(__file__).resolve().parents[1]
def latest_inputs():
    pointer = ROOT / "data/mosaic/current.json"
    if not pointer.is_file():
        return []
    try:
        current = json.loads(pointer.read_text(encoding="utf-8"))
        manifest_path = (pointer.parent / current["manifest"]).resolve()
        if not manifest_path.is_relative_to(pointer.parent.resolve()):
            return []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return [manifest_path.parent / value for value in manifest["result"]["review_bundle"].values()]
    except (ValueError, OSError, KeyError, TypeError):
        return []


STATUS = {"pending": "待审核", "accepted": "已审核 · 通过", "rejected": "已审核 · 拒绝"}
KINDS = {"positive": "正例 pos", "negative": "负例 neg", "other": "其他记录"}


def frame(rows):
    # Heterogeneous source quantities must remain readable without Arrow type errors.
    return pd.DataFrame([{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list))
                             else "" if v is None else str(v)) for k, v in row.items()} for row in rows])


def show_json(title, value, expanded=False):
    with st.expander(title, expanded=expanded):
        if value is None:
            st.caption("原始记录未提供此字段。")
        else:
            st.json(value)


def show_import_report(report):
    st.success(f"导入完成：新增 {report['inserted']} 条，跳过已有 ID {report['skipped']} 条。")
    if report["changed_duplicates"]:
        st.warning("以下 ID 的输入内容与库内快照不同，已保留库内快照与审核状态。需要审核新版本时请另建数据库。")
        st.dataframe(frame(report["changed_duplicates"]), hide_index=True, width="stretch")


def import_panel(database, suffix):
    with st.form("import_" + suffix):
        paths = st.text_area("数据文件或目录（每行一个路径）", "\n".join(str(p) for p in latest_inputs()),
                             height=130, key="inputs_" + suffix,
                             help="支持 JSON 单记录、JSON 数组和 JSONL；目录递归扫描。只选择记录数据目录。")
        uploads = st.file_uploader("也可以上传 JSON / JSONL", type=["json", "jsonl"],
                                   accept_multiple_files=True, key="uploads_" + suffix)
        mode = st.selectbox("本批记录类型", ["auto", "positive", "negative", "other"],
                            format_func=lambda v: "自动识别（保留原始标签）" if v == "auto" else KINDS[v],
                            key="kind_" + suffix)
        submitted = st.form_submit_button("导入数据库", type="primary")
    if submitted:
        try:
            # Uploaded files take precedence, so the prefilled local paths are not imported accidentally.
            if uploads:
                report = import_documents(database, ((f"upload:{f.name}", f.getvalue().decode("utf-8-sig"))
                                                       for f in uploads), mode)
            else:
                report = import_paths(database, [p.strip() for p in paths.splitlines() if p.strip()], mode)
            st.session_state["active_db"] = str(Path(database).expanduser().resolve())
            st.session_state["import_report"] = report
            st.session_state["open_imported_db"] = True
            st.rerun()
        except (ValueError, OSError, sqlite3.Error, UnicodeError) as exc:
            st.error(f"导入失败，记录写入已回滚：{exc}")


def database_connection():
    if st.session_state.pop("open_imported_db", False):
        st.session_state["connection_mode"] = "打开已有数据库"
    st.sidebar.title("流程批改")
    st.sidebar.markdown("[使用帮助](?help=1)")
    reviewer = st.sidebar.text_input("审核人姓名", key="reviewer", placeholder="填写真实姓名或团队标识")
    active = st.session_state.get("active_db")
    if not active and not st.session_state.get("auto_connection_checked"):
        st.session_state["auto_connection_checked"] = True
        default_path = os.environ.get("AUDIT_DB", str(db.DEFAULT_DB))
        try:
            db.validate_database(default_path)
            active = st.session_state["active_db"] = str(Path(default_path).expanduser().resolve())
        except (ValueError, OSError, sqlite3.Error):
            pass
    with st.sidebar.expander("数据库连接", expanded=not bool(active)):
        connection_mode = st.radio("连接方式", ["打开已有数据库", "首次建库并导入"], key="connection_mode")
        database = st.text_input("SQLite 数据库路径", os.environ.get("AUDIT_DB", str(db.DEFAULT_DB)),
                                 key="database_path")
        if connection_mode == "打开已有数据库" and st.button("打开数据库", key="open_db"):
            try:
                db.validate_database(database)
                st.session_state["active_db"] = str(Path(database).expanduser().resolve())
                st.session_state.pop("current_record", None)
                st.session_state.pop("queue_signature", None)
                st.rerun()
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(f"无法打开数据库：{exc}")
    if connection_mode == "首次建库并导入":
        st.subheader("首次导入")
        st.caption("选择数据库保存位置后导入。重复 ID 会跳过，已有审核结果会保留。")
        import_panel(database, "initial")
        st.stop()
    if not active:
        st.subheader("打开审核数据库")
        st.write("在侧边栏打开已有数据库，或选择「首次建库并导入」。")
        st.caption("导入完成后，后续审核直接访问 SQLite。原始文件不参与同步。")
        st.stop()
    try:
        db.validate_database(active)
    except (ValueError, OSError, sqlite3.Error) as exc:
        st.error(f"当前数据库不可用：{exc}")
        st.stop()
    return active, reviewer


def sidebar_filters(database):
    options = db.filter_options(database)
    st.sidebar.divider()
    st.sidebar.subheader("本轮范围")
    states = {"pending": "待审核", "": "全部状态", "reviewed": "已审核", "accepted": "通过", "rejected": "拒绝"}
    status = st.sidebar.selectbox("审核状态", list(states), format_func=states.get, key="filter_status")
    record_type = st.sidebar.selectbox("记录类型", [""] + list(KINDS),
                                        format_func=lambda v: KINDS.get(v, "全部类型"), key="filter_kind")
    risk = st.sidebar.selectbox("风险类别", [""] + options["risks"],
                                format_func=lambda v: risk_name(v) if v else "全部风险", key="filter_risk")
    with st.sidebar.expander("更多筛选"):
        tier = st.selectbox("当前 tier", [""] + options["tiers"],
                            format_func=lambda v: v or "全部层级", key="filter_tier")
        bool_labels = {None: "全部", 1: "有", 0: "无"}
        blockers = st.selectbox("Gold blockers", [None, 1, 0], format_func=bool_labels.get, key="filter_blockers")
        symbolic = st.selectbox("Symbolic violations", [None, 1, 0], format_func=bool_labels.get, key="filter_symbolic")
        search = st.text_input("查找 ID / parent_id", key="filter_search")
    return {"status": status, "record_type": record_type, "tier": tier, "risk": risk,
            "has_gold_blockers": blockers, "has_symbolic_violations": symbolic, "search": search}


def move_record(offset):
    count = len(st.session_state.get("review_queue", []))
    st.session_state["queue_index"] = max(0, min(count - 1, st.session_state.get("queue_index", 0) + offset))


def record_page(database, filters):
    # Freeze IDs for a round: deciding a pending record must not remove it or break Back.
    signature = json.dumps([database, filters], sort_keys=True)
    if st.session_state.get("queue_signature") != signature:
        st.session_state["queue_signature"] = signature
        st.session_state["review_queue"] = [r["record_id"] for r in db.query_records(database, filters)]
        st.session_state["queue_index"] = 0
    ids = st.session_state["review_queue"]
    with st.sidebar.expander("跳转与刷新"):
        with st.form("jump_form"):
            target = st.number_input("跳转到第几条", min_value=1, max_value=max(1, len(ids)), value=1, step=1)
            if st.form_submit_button("跳转", disabled=not ids):
                st.session_state["queue_index"] = int(target) - 1
        if st.button("刷新本轮队列", key="refresh_queue"):
            st.session_state.pop("queue_signature", None)
            st.rerun()
        st.caption("本轮保留已批改记录，方便回看。刷新后重新应用筛选。")
    if not ids:
        st.info("当前范围没有记录。调整筛选条件后即可继续批改。")
        return None
    index = min(st.session_state["queue_index"], len(ids) - 1)
    with st.container(key="pager"):
        previous, position, following = st.columns([1, 2, 1])
        previous.button("上一条", key="nav_prev", disabled=index == 0, on_click=move_record, args=(-1,), width="stretch")
        position.markdown(f'<div class="page-position">第 <strong>{index + 1}</strong> / {len(ids)} 条</div>', unsafe_allow_html=True)
        following.button("下一条", key="nav_next", disabled=index == len(ids) - 1, on_click=move_record, args=(1,), width="stretch")
    row = db.get_record(database, ids[index])
    st.session_state["current_record"] = ids[index]
    return row


def review_controls(database, row, reviewer):
    suffix = hashlib.sha256((database + row["record_id"]).encode()).hexdigest()[:16] + "_" + str(row["revision"])
    if row["status"] != "pending":
        message = f"{STATUS[row['status']]} · {row['reviewer']}"
        (st.success if row["status"] == "accepted" else st.warning)(message)
        st.caption(row["reviewed_at"])
        st.write("审核意见：", row["comment"] or "未填写")
        if st.button("撤销审核", key="undo_" + suffix, disabled=not reviewer.strip()):
            try:
                db.review_record(database, row["record_id"], "undo", reviewer,
                                 "撤销审核，恢复待审核状态", row["revision"])
                st.session_state["notice"] = f"已撤销 {row['record_id']} 的审核；操作历史已保留。"
                st.rerun()
            except (ValueError, sqlite3.Error) as exc:
                st.error(str(exc))
        return
    if not reviewer.strip():
        st.caption("在侧边栏填写审核人，即可提交。")
    with st.form("review_" + suffix):
        comment = st.text_input("审核意见（可选）", key="comment_" + suffix)
        accept, reject = st.columns(2)
        yes = accept.form_submit_button("通过并下一条", type="primary", disabled=not reviewer.strip(),
                                        width="stretch")
        no = reject.form_submit_button("拒绝并下一条", disabled=not reviewer.strip(), width="stretch")
    if yes or no:
        try:
            db.review_record(database, row["record_id"], "accept" if yes else "reject", reviewer,
                             comment, row["revision"])
            st.session_state["notice"] = f"已保存 {row['record_id']} 的{'通过' if yes else '拒绝'}决定。"
            queue = st.session_state.get("review_queue", [])
            index = st.session_state.get("queue_index", 0)
            next_pending = next((i for i in range(index + 1, len(queue))
                                 if db.get_record(database, queue[i])["status"] == "pending"), None)
            if next_pending is not None:
                st.session_state["queue_index"] = next_pending
            else:
                st.session_state["notice"] += " 当前记录之后没有待审核项，可回看或刷新队列。"
            st.rerun()
        except (ValueError, sqlite3.Error) as exc:
            st.error(str(exc))


def step_card(step, record, highlighted=False, tag_text="核对位置"):
    title, summary = step_summary(step, record)
    vessel = step.get("vessel", step.get("to_vessel", ""))
    nodes = as_dict(as_dict(field(record, "hardware")).get("nodes"))
    node = as_dict(nodes.get(str(vessel)))
    params = as_dict(node.get("params"))
    capacity = params.get("capacity_mL")
    facts = (f"容器 {vessel}" if vessel else "") + (f" · 容量 {capacity} mL" if capacity is not None else "")
    apparatus = {"microreactor": "微型反应器", "well_plate": "孔板", "vial": "反应瓶", "round_bottom_flask": "圆底烧瓶"}.get(node.get("apparatus_kind"))
    if apparatus:
        facts += " · " + apparatus
    if node.get("capacity_scope") == "per_well":
        facts += "（单孔容量）"
    evidence = as_dict(step.get("meta")).get("evidence")
    tag = f'<span class="focus-tag">{escape(tag_text)}</span>' if highlighted else ""
    st.markdown(f'<div class="flow-step {"focused" if highlighted else ""}">'
                f'<div class="step-heading"><strong>{step["_number"]}. {escape(title)}</strong>{tag}</div>'
                f'<div class="step-value">{escape(summary or "未提供可展示的用量或条件")}</div>'
                f'<div class="step-facts">{escape(facts)}</div>'
                + (f'<div class="step-quote">原文：{escape(text(evidence, 230))}</div>' if evidence else "")
                + '</div>', unsafe_allow_html=True)


def show_comparison(point):
    changes = point.get("changes", [])
    if not changes:
        return
    quantity = point["key"].startswith("quantity:")
    left_label, right_label = ("原文用量", "当前流程") if quantity else ("父记录", "当前记录")
    html = '<div class="comparison">'
    for change in changes:
        html += (f'<div class="change-name">{escape(change["field"])}</div><div class="compare-values">'
                 f'<div><span>{left_label}</span><p>{escape(change["before"])}</p></div>'
                 f'<div class="changed-value"><span>{right_label}</span><p>{escape(change["after"])}</p></div></div>')
    st.markdown(html + '</div>', unsafe_allow_html=True)


def focus_review(database, row, reviewer):
    record = json.loads(row["raw_json"])
    parent_row = db.get_record(database, row["parent_id"]) if row["parent_id"] else None
    parent = json.loads(parent_row["raw_json"]) if parent_row else None
    points = review_points(record, parent)
    steps = procedure(record)
    label = as_dict(record.get("label"))
    risk = as_dict(record.get("label")).get("risk_l2")
    title = risk_name(str(risk)) if risk else "正例 · 流程与来源核对" if row["record_type"] == "positive" else "流程与来源核对"
    if quality(record).get("conversion_status") == "incomplete_not_a_positive":
        title = "提取工具未完成 · 尚未计入正例"
    st.markdown(f'<div class="record-heading"><strong>{escape(title)}</strong>'
                f'<span>{escape(STATUS[row["status"]])}</span></div>'
                f'<div class="record-id">{escape(row["record_id"])}</div>', unsafe_allow_html=True)
    mechanism = as_dict(record.get("mutation")).get("mechanism_id")
    if quality(record).get("representation_complete"):
        st.caption("动作已表达 · " + ("参数齐全" if quality(record).get("parameters_complete") else "缺失参数已显式标记")
                   + " · 设备执行支持单独核验")
    if mechanism:
        st.caption("扰动方式：" + mechanism_name(str(mechanism)))
    suffix = hashlib.sha256((database + row["record_id"]).encode()).hexdigest()[:12] + str(row["revision"])
    selected = st.selectbox("核对位置", list(range(len(points))),
                            format_func=lambda i: f"{i + 1} / {len(points)} · {points[i]['title']}", key="point_" + suffix)
    point = points[selected]
    reason = explain_risk(record, point, parent)
    targets = focus_indices(steps, point)
    flow_col, review_col = st.columns([1.25, 1], gap="large")
    with flow_col:
        source_text = field(record, "source_text")
        if source_text:
            with st.expander("对照实验原文（提取依据）"):
                st.text_area("完整原文", str(source_text), height=240, disabled=True,
                             key="source_" + suffix, label_visibility="collapsed")
                st.caption("步骤、用量和器材应由这段文本支持。ORD 结构字段仅用于独立比较。")
        st.markdown("#### 流程片段")
        if point.get("removed_step") and parent:
            st.caption("父记录中的以下步骤已被删除：")
            step_card(point["removed_step"], parent, True, "已被移除")
        if steps:
            target = targets[0] if targets else 0
            st.caption(f"已定位第 {target + 1} 步 · 全流程共 {len(steps)} 步")
            step_card(steps[target], record, not point.get("removed"))
            neighbors = [i for i in range(max(0, target - 1), min(len(steps), target + 2)) if i != target]
            if neighbors:
                with st.expander("查看相邻步骤", expanded=risk in ("B5", "D1")):
                    for index in neighbors:
                        step_card(steps[index], record, index in targets and not point.get("removed"))
            with st.expander(f"查看完整流程（{len(steps)} 步）"):
                for step in steps:
                    action, description = step_summary(step, record)
                    st.markdown(f"**{step['_number']}. {action}**　{description}")
        else:
            st.info("没有可解析的结构化步骤。请展开原始记录核对 XDL。")
        missing_ids = [s for s in point.get("step_ids", []) if not any(step["_id"] == s for step in steps)]
        if point["key"].startswith("/steps/") and missing_ids:
            st.caption("改动涉及已删除或已改名步骤，当前展示删除位置附近的上下文。")
    with review_col:
        if reason:
            if reason["label_type"] == "soft":
                status = "记录标为已校准" if reason.get("calibrated") is True else "未校准"
                provenance = f"soft 条件扰动假设 · {status} · 不等于已观察到的失败"
            else:
                provenance = f"{reason['origin']} · {reason['rule_id'] or reason['judge'] or '规则来源未提供'}"
            st.markdown('<div class="risk-explanation"><h4>风险原因（原标注）</h4>'
                        f'<p>{escape(reason["summary"])}</p><div class="reason-provenance">{escape(provenance)}</div>'
                        f'<div class="reason-condition">{escape(reason["condition"])}</div></div>', unsafe_allow_html=True)
            with st.expander("核对规则与适用条件"):
                st.write(reason["review_hint"])
                for affected in reason.get("affected_steps", []):
                    st.write(f"第 {affected['number']} 步（{affected['step_id']}）：{affected['request']}")
                if reason.get("context"):
                    names = {"pressure_control": "压力控制", "reflux": "回流", "pure_solvent": "纯溶剂场景",
                             "ignition_source": "点火源", "vapor_exposed": "蒸气暴露", "oxygen_present": "有氧环境"}
                    for key, value in reason["context"].items():
                        st.write(f"{names.get(key, key)}：{text(value)}")
                st.caption(f"原始判定器：{reason['judge'] or '未提供'} · 标签类型：{reason['label_type'] or '未提供'}")
                if reason["scope"]:
                    st.caption("原始适用范围：" + text(reason["scope"], 800))
        else:
            st.markdown("#### 核对依据")
            st.write(point["note"])
        show_comparison(point)
        evidence = point.get("evidence", [])
        entry = reason.get("selected_evidence", {}) if reason else next((e for e in evidence if isinstance(e, dict) and
                    as_dict(e.get("values")).get("step_id") in point.get("step_ids", [])), evidence[0] if evidence else {})
        values = as_dict(as_dict(entry).get("values"))
        facts = [(FIELD_NAMES.get(k, k), text(v, 180)) for k, v in values.items()
                 if k not in ("step", "step_id", "group_evidence")][:6]
        if facts:
            st.markdown('<div class="evidence-facts">' + ''.join(
                f'<div><span>{escape(k)}</span><strong>{escape(v)}</strong></div>' for k, v in facts) + '</div>',
                unsafe_allow_html=True)
        contract = point.get("contract")
        if contract:
            st.caption(f"原始标注：容器 {contract.get('vessel', '未提供')}，初始体积 {contract.get('initial_volume', '未提供')}")
            st.write("需核对的输入位置：", contract.get("producer_xpath", "未提供"))
        source = as_dict(entry).get("source_url")
        if isinstance(source, str) and source.startswith(("https://", "http://")):
            st.link_button("查看该依据的来源", source)
        if label.get("label_type") == "soft":
            st.caption("soft 条件扰动：实验结果未知，请核对假设与证据。")
        elif row["record_type"] == "negative":
            st.caption("确认错误流程与风险标注匹配；通过后仍保留负例标签。")
        review_controls(database, row, reviewer)
    with st.expander("完整证据与其他资料"):
        st.caption(f"导入层级 {row['tier']} · 当前层级 {row['effective_tier']}")
        show_json("当前审核点的完整证据", point)
        if reason:
            show_json("风险原因的原始依据与解释来源", reason)
        detail(database, row)


def detail(database, row):
    record = json.loads(row["raw_json"])
    st.subheader("记录详情")
    reference = as_dict(field(record, "reference_metadata"))
    yield_value = reference.get("yield_percent", field(record, "yield_percent"))
    st.write("Yield (%)：", "未提供" if yield_value is None else str(yield_value))
    smiles = reference.get("reaction_smiles", field(record, "reaction_smiles"))
    if smiles:
        st.code(str(smiles), language=None, wrap_lines=True)
    else:
        st.caption("原始记录未提供 reaction_smiles。")
    if reference:
        st.caption("以上 ORD 产率和 SMILES 是参考注释，不参与流程生成。")
    checks_tab, steps_tab, risks_tab, raw_tab, history_tab = st.tabs(
        ["核对与质量", "步骤与器材", "负例与父记录", "原始记录", "审核历史"])
    with checks_tab:
        cross = field(record, "crosscheck")
        q = quality(record)
        show_json("Gold blockers（crosscheck + quality）", {
            "crosscheck": as_dict(cross).get("gold_blockers"), "quality": q.get("gold_blockers")}, expanded=True)
        st.caption("通过审核会保留 blocker、硬件验证和可行性等原始字段；gold 表示本工具的人工数据审核通过。")
        show_json("Crosscheck · 全部核对结果", cross, expanded=True)
        show_json("Quality · symbolic / unknown / hardware / feasibility / manual_review", field(record, "quality"), True)
        show_json("来源与抽取证据", {"source": field(record, "source"), "extraction": field(record, "extraction"),
                                      "source_evidence": field(record, "source_evidence")})
        if reference:
            show_json("ORD 参考注释（与文本独立比较）", reference)
    with steps_tab:
        rows = step_rows(record)
        if rows:
            st.dataframe(frame(rows), hide_index=True, width="stretch")
            st.caption("用量与容量均取自原始记录。空容量表示缺失；本页未推算密度或累计液体体积。")
        else:
            st.info("未提供结构化 steps；可在下方查看 XDL 和完整原始记录。")
        show_json("完整 steps（含每步其他字段）", field(record, "steps"))
        show_json("器材、容量与验证状态", field(record, "hardware"), True)
        show_json("扩展原子操作定义（可表示不等于可执行）", field(record, "operation_definitions"))
        show_json("来源缺失参数及标识", quality(record).get("missing_parameters"))
        show_json("Reagents · 全部原料", field(record, "reagents"), True)
        xdl = field(record, "xdl")
        if xdl:
            with st.expander("XDL 程序", expanded=not bool(rows)):
                st.code(str(xdl), language="xml", wrap_lines=True)
    with risks_tab:
        st.write("Parent ID：", row["parent_id"] or "未提供")
        show_json("风险标签 label", record.get("label"), True)
        show_json("审计 audit（child_risks / parent_risks）", record.get("audit"), True)
        show_json("改动 diff / mutation / contract", {"diff": record.get("diff"),
                   "mutation": record.get("mutation"), "contract": record.get("contract")})
        if row["parent_id"]:
            parent = db.get_record(database, row["parent_id"])
            if parent:
                parent_record = json.loads(parent["raw_json"])
                with st.expander("父记录对照（数据库快照）", expanded=True):
                    st.caption(f"{parent['record_id']} · {STATUS[parent['status']]}")
                    parent_steps = step_rows(parent_record)
                    if parent_steps:
                        st.dataframe(frame(parent_steps), hide_index=True, width="stretch")
                    st.json(parent_record)
            else:
                st.caption("父记录尚未导入此数据库。可通过数据管理页补充导入；本页不会读取源文件。")
    with raw_tab:
        st.caption(f"导入时间：{row['imported_at']} ｜ 来源：{row['source_file']} ｜ 修订号：{row['revision']}")
        st.caption("以下为不可变的导入快照。当前审核决定保存在数据库中，导出时才合并。")
        st.json(record, expanded=False)
    with history_tab:
        history = db.review_history(database, row["record_id"])
        if history:
            st.dataframe(frame(history), hide_index=True, width="stretch")
        else:
            st.caption("还没有人工审核操作。")


def export_panel(database, filters):
    st.subheader("从数据库导出")
    st.caption("导出为新的带时间戳文件或目录；不会更新初始 JSON。")
    scope = st.radio("导出范围", ["当前筛选结果", "全部记录"], horizontal=True, key="export_scope")
    with st.form("export_form"):
        output = st.text_input("服务器导出父目录", str(DEFAULT_EXPORT), key="export_dir")
        mode = st.radio("JSON 文件组织", ["single", "split"],
                        format_func=lambda v: "单个 JSON 数组文件" if v == "single" else "每条记录一个 JSON 文件",
                        key="export_mode")
        submitted = st.form_submit_button("生成时间戳导出", type="primary")
    if submitted:
        try:
            # One SELECT provides a consistent export snapshot even with concurrent reviewers.
            rows = db.query_records(database, filters if scope == "当前筛选结果" else {}, include_raw=True)
            run = export_rows(rows, output, mode)
            st.session_state["export_result"] = {
                "database": database, "run": str(run), "count": len(rows),
                "json": json_bytes(rows), "csv": csv_bytes(rows), "stamp": timestamp()}
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(f"导出失败：{exc}")
    result = st.session_state.get("export_result")
    if result and result["database"] == database:
        st.success(f"已导出 {result['count']} 条记录至 {result['run']}")
        st.caption("以下下载的是本次导出快照；后续审核后请重新生成导出。")
        st.download_button("下载 JSON 数组", result["json"], f"records_{result['stamp']}.json", "application/json")
        st.download_button("下载审核汇总 CSV", result["csv"], f"reviews_{result['stamp']}.csv", "text/csv")


def main():
    st.set_page_config(page_title="反应流程人工审核", layout="wide")
    st.markdown("""<style>
    .stApp { background: #fafbf9; color: #1b2926; }
    h1, h2, h3 { color: #183a33; }
    h1 { font-size: 1.6rem !important; }
    h4 { font-size: 1.05rem !important; }
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #52645c; }
    code { overflow-wrap: anywhere; }
    [data-testid="stTextArea"] textarea:disabled { -webkit-text-fill-color: #263b34 !important; color: #263b34 !important; opacity: 1 !important; }
    :focus-visible { outline: 2px solid #216858; outline-offset: 2px; }
    ::selection { background: #c5e3d8; color: #183a33; }
    [data-testid="stMainBlockContainer"] { padding-top: 4.5rem; max-width: 1280px; }
    .page-position { text-align: center; padding: 7px; color: #53645d; }
    .record-heading { display: flex; justify-content: space-between; gap: 12px; margin-top: 12px; }
    .record-heading strong { font-size: 1.15rem; }
    .record-heading span, .record-id { color: #53645d; font-size: 0.85rem; }
    .record-id { margin: 5px 0 12px; overflow-wrap: anywhere; }
    .flow-step { border: 1px solid #d9e0dc; border-radius: 8px; padding: 12px 14px; margin: 0 0 10px; background: white; }
    .flow-step.focused { border-color: #b7a052; background: #fff8e4; }
    .step-heading { display: flex; justify-content: space-between; gap: 8px; }
    .focus-tag { color: #735b10; font-size: 0.78rem; }
    .step-value { margin-top: 6px; overflow-wrap: anywhere; }
    .step-facts, .step-quote { margin-top: 6px; font-size: 0.82rem; color: #53645d; overflow-wrap: anywhere; }
    .step-quote { padding-top: 6px; border-top: 1px solid #d9e0dc; }
    .comparison { margin: 8px 0 14px; }
    .change-name { font-size: 0.85rem; font-weight: 600; margin: 8px 0 5px; }
    .compare-values { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .compare-values > div { padding: 9px 11px; background: #edf1ee; border-radius: 6px; min-width: 0; }
    .compare-values .changed-value { background: #fff1c8; }
    .compare-values span { color: #53645d; font-size: 0.78rem; }
    .compare-values p { margin: 4px 0 0; overflow-wrap: anywhere; font-weight: 600; }
    .evidence-facts { margin: 8px 0 12px; }
    .evidence-facts > div { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; }
    .evidence-facts span { color: #53645d; }
    .evidence-facts strong { text-align: right; overflow-wrap: anywhere; }
    .risk-explanation h4 { margin: 0 0 10px; padding: 0; }
    .risk-explanation p { margin: 0 0 6px; }
    .reason-provenance, .reason-condition { color: #52645c; font-size: 0.83rem; margin-top: 6px; }
    [data-testid="stForm"] { border: 0; padding: 0; }
    @media (max-width: 640px) {
        .st-key-pager [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: 0.5rem; }
        .st-key-pager [data-testid="stColumn"] { min-width: 0 !important; width: 0 !important; flex: 1 1 0 !important; }
        .page-position { font-size: 0.85rem; white-space: nowrap; }
    }
    </style>""", unsafe_allow_html=True)
    if st.query_params.get("help") == "1":
        st.markdown((Path(__file__).resolve().parent / "HELP.md").read_text(encoding="utf-8"))
        return
    database, reviewer = database_connection()
    if "import_report" in st.session_state:
        show_import_report(st.session_state.pop("import_report"))
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    stats = db.statistics(database)
    reviewed = stats["accepted"] + stats["rejected"]
    st.sidebar.caption(f"已审 {reviewed} / {stats['total']} · 通过 {stats['accepted']} · 拒绝 {stats['rejected']}")
    page = st.sidebar.radio("工作页", ["逐条审核", "导出", "数据管理"], key="workspace_page", label_visibility="collapsed")
    filters = sidebar_filters(database)
    if page == "逐条审核":
        row = record_page(database, filters)
        if row:
            focus_review(database, row, reviewer)
    elif page == "导出":
        export_panel(database, filters)
    else:
        st.subheader("补充导入记录")
        st.caption("这是显式的一次性导入。已有 ID 的快照与审核状态会保留；不会建立文件同步。")
        import_panel(database, "additional")


if __name__ == "__main__":
    main()
