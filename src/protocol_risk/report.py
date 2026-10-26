"""Readable statistics and honest milestone status from generated artifacts."""
from __future__ import annotations

from collections import Counter

from .io import ROOT, load_library, read_json, read_jsonl, write_json


def report():
    stats = read_json(ROOT / "reports/stats.json")
    audit_path = ROOT / "reports/audit.json"
    audit = read_json(audit_path) if audit_path.exists() else {"passed": False, "full_specification_accepted": False}
    library = load_library("risks.yaml")["risks"]
    methods = stats["positive_methods"]
    native_path = ROOT / "data/native_negatives.jsonl"
    native = list(read_jsonl(native_path)) if native_path.exists() else []
    native_counts = Counter(n["label"]["risk_l2"] for n in native)
    coverage = Counter(stats["observed_risk_counts"])
    coverage.update(native_counts)
    sop_path = ROOT / "data/sop/negatives.jsonl"
    sop = list(read_jsonl(sop_path)) if sop_path.exists() else []
    sop_literals = Counter(n["label"]["risk_l2"] for n in sop if n["origin"] == "published_sop_fragment")
    sop_instances = Counter(n["label"]["risk_l2"] for n in sop if n["origin"] == "instantiated_sop")
    coverage.update(sop_literals)
    dataset_coverage = coverage + sop_instances
    source_missing = {r: max(0, 10 - coverage[r]) for r in library if coverage[r] < 10}
    missing = {r: max(0, 10 - dataset_coverage[r]) for r in library if dataset_coverage[r] < 10}
    manifest = {"version": 2, "positive_candidates": {"path": "data/positives.jsonl", "count": stats["positive_xdl"], "tier": "silver unless supported by a recorded review"},
                "negative_partitions": [{"path": "data/negatives.jsonl", "format": "protocol_risk_ir", "count": stats["observed_parent_negatives"]},
                                        {"path": "data/native_negatives.jsonl", "format": "native_author_xdl", "count": len(native)},
                                        {"path": "data/sop/negatives.jsonl", "format": "protocol_risk_ir_with_sop_context", "count": len(sop),
                                         "literal_source_fragments": sum(sop_literals.values()), "instantiated_scenarios": sum(sop_instances.values())}],
                "control_partition": {"path": "data/controls/negatives.jsonl", "count": stats["control_negatives"], "counts_toward_source_quota": False},
                "source_derived_risk_counts": dict(coverage), "source_derived_total": sum(coverage.values()),
                "instantiated_sop_risk_counts": dict(sop_instances), "instantiated_sop_total": sum(sop_instances.values()),
                "risk_counts": dict(dataset_coverage), "negative_total": sum(dataset_coverage.values()),
                "source_only_risk_gaps": source_missing,
                "sop_parent_diversity": read_json(ROOT / "reports/sop_dataset.json").get("unique_parents_per_risk", {}) if sop else {},
                "remaining_risk_gaps": missing, "human_review": "deferred; no fabricated approval"}
    platform_path = ROOT / "reports/native_platform.json"
    native_platform = read_json(platform_path) if platform_path.exists() else None
    if native_platform:
        manifest["native_platform_reference"] = {"path": "data/publications/platform_positives.jsonl", "count": native_platform["compiled"],
            "validation_path": "data/publications/platform_validation.jsonl", "source_partitions": native_platform["compiled_source_partitions"],
            "tier": "compiled_source_reference; human review deferred; no full chemical feasibility certificate"}
    write_json(ROOT / "data/dataset.json", manifest)
    write_json(ROOT / "reports/dataset_coverage.json", manifest)
    lines = ["# 数据集统计", "", "本报告由实际产物自动生成。", "",
             f"- 固定来源：46 个 ORD 数据文件，{stats['raw_reactions']:,} 条真实 raw 反应。",
             f"- 选中 raw / XDL：{stats['raw_selected']} / {stats['positive_xdl']}。",
             f"- 提取方式：文本 {methods.get('llm_evidence_constrained', 0)}；结构化反应阶段 {methods.get('ord_structured', 0)}。",
             f"- 全部初始用量通过独立原文数值核对：{stats.get('independent_amounts_verified', 0)} 条；其余仍待补证。",
             f"- 去重后独立流程 {stats.get('unique_canonical_protocols', stats['positive_xdl'])}；反应 SMILES {stats.get('unique_reaction_smiles', '待统计')}；选中数据集 {stats.get('selected_source_datasets', '待统计')}。",
             f"- 严格 gold：{stats['strict_gold']}；silver：{stats['silver']}。",
             f"- 研究候选负例合计：{sum(dataset_coverage.values())}，{'各类至少 10 条' if not missing else '仍有类别缺口'}；直接来源派生 {sum(coverage.values())}，来源约束下的生成场景 {sum(sop_instances.values())}。",
             f"- 直接来源分区：ORD {stats['observed_parent_negatives']}；作者原生 XDL {len(native)}；原文 SOP 片段 {sum(sop_literals.values())}。",
             f"- 独立手写控制负例：{stats['control_negatives']}，不算作真实 ORD 派生 gold。",
             f"- 器材 {stats['hardware_entries']} 条，人工 verified {stats['hardware_human_verified']} 条；原子操作 {stats['primitive_operations']}；风险子类 {stats['risk_categories']}。",
             f"- 假负样本过滤检查固定来源中的 {stats['success_filter_observations']:,} 条 ≥30% 成功观测。",
             f"- 内部完整性审计：{'通过' if audit['passed'] else '未通过'}；完整规范验收：{'通过' if audit['full_specification_accepted'] else '尚未通过'}。", "",
             "| 风险 | 类别 | ORD 派生 | 原生 XDL | SOP 原文片段 | SOP 生成场景 | 候选合计 | 手写控制 | 距 10 条缺口 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for risk, spec in library.items():
        observed = stats["observed_risk_counts"].get(risk, 0)
        lines.append(f"| {risk} | {spec['name']} | {observed} | {native_counts[risk]} | {sop_literals[risk]} | {sop_instances[risk]} | {dataset_coverage[risk]} | {stats['control_risk_counts'].get(risk, 0)} | {max(0, 10-dataset_coverage[risk])} |")
    lines += ["", "C1/C2/C3/C4/C6 是未校准的条件扰动，不能把这五类的候选数量解读为已证实的失败数量。",
              "所有 silver 父流程仍需独立核对主要用量、完整流程和器材；研究候选 benchmark_eligible=false。",
              "当前按用户要求优先构造数据。带厂商出处并已核对的参数可以支持临时研究约束，明确标记 source_reviewed_provisional；人工审核暂缓，verified 不会自动置 true。",
              "作者原生 D2 删除向初始空容器输送物料的唯一语句，保留后续蒸发，错误依据是明确的物料输入缺失；其检查范围与 ORD IR 检查分开记录。", "",
              "B5 使用 10 组数值不同的原文稀释片段。B2 有 1 个 DMSO 解冻父场景、12 个温度变体；B3 有 6 种溶剂、2 类点火源的 12 个场景。B2/B3 的 30 C 等设定值是明确标注的实例参数，不是原文实验值，也不计入直接来源样例配额。",
              "SOP 仅表达已解析片段；缓慢加料、冷却和定容等未量化指令保留为 unresolved_instructions。B3 点火和预装物料属于侧车上下文；单独 XDL 不证明全部设备行为。", "",
              "![实际风险覆盖](risk_coverage.png)", "", "原子操作统计见 [atomic_operations.md](atomic_operations.md)。",
              "", "人工复核队列在 manual_review.csv；尚未填写的记录不算作人工通过。"]
    if native_platform:
        lines += ["", f"原配套平台检查：{native_platform['programs_checked']} 份作者原生程序中，{native_platform['typed_parse_passed']} 份通过类型解析，{native_platform['compiled']} 份在原图上通过编译与内置检查。",
                  f"通过程序的作者分区：{native_platform['compiled_source_partitions']}；编译参考数据与 ORD 的 140 组候选分别保存，不累计冒充完整 gold。",
                  "详细结果见 [native_platform.md](native_platform.md)。原始编译器源码未改动；格式别名、外层 XML 包装与缺省异步进程 ID 的适配均有记录。"]
    (ROOT / "reports/stats.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    counts = Counter()
    for p in read_jsonl(ROOT / "data/positives.jsonl"):
        counts.update(s["op"] for s in p["steps"])
    atoms = load_library("primitives.yaml")["operations"]
    atom_lines = ["# 原子操作库统计", "", "单一权威定义：libraries/primitives.yaml。", "",
                  "| 原子操作 | 本批已选流程出现次数 | 标准 XDL 映射 |", "|---|---:|---|"]
    for op, spec in atoms.items():
        atom_lines.append(f"| {op} | {counts[op]} | {', '.join(spec['xdl_steps']) or '无确认映射，导出时隔离'} |")
    atom_lines += ["", "覆盖率统计的分母仅为已接受 IR 中的操作。不能据此声称对全部原始文本文库已达到 ≥98% 的抽取覆盖率。"]
    (ROOT / "reports/atomic_operations.md").write_text("\n".join(atom_lines) + "\n", encoding="utf-8")
    _publication_report()
    _native_platform_report(native_platform)
    _contrast_report()
    _judge_report()
    plot_stats = dict(stats, observed_risk_counts=dict(coverage), instantiated_sop_risk_counts=dict(sop_instances))
    _coverage_plot(plot_stats, list(library))
    status = {"goal": "active", "internal_integrity_passed": audit["passed"],
              "full_specification_accepted": audit["full_specification_accepted"],
              "completed": ["API authentication and invalid-key control", "pinned raw corpus", "reusable extraction and offline rebuild", "XDL subset exports", "independent libraries", "single-fault replay checks", "HTE baseline with calibration"],
              "focus": "dataset construction; human reviews deferred by user",
              "basic_dataset_coverage_complete": not missing,
              "native_platform_compiled": native_platform["compiled"] if native_platform else 0,
              "remaining": ["Improve independent source-parent diversity for " + ", ".join(source_missing),
                            "Deferred: independent review and hardware verification to promote 100+ strict gold procedures",
                            "10+ genuinely eligible source-derived examples for every risk; controls cannot fill this quota",
                            "100 actual human negative reviews and measured hard-label error rate",
                            "Per-C-subclass causal calibration data and judge admission; current model not admitted"],
              "acceptance": audit.get("acceptance", {})}
    write_json(ROOT / "reports/task_status.json", status)
    return {"stats": "reports/stats.md", "status": "reports/task_status.json", "full_acceptance": audit["full_specification_accepted"]}


def _native_platform_report(data):
    if not data:
        return
    rows = list(read_jsonl(ROOT / "data/publications/platform_validation.jsonl"))
    lines = ["# 原生平台参考流程", "",
             f"检查 {data['programs_checked']} 份原生程序；类型解析通过 {data['typed_parse_passed']}；原图编译通过 {data['compiled']}；未通过或缺图 {data['failed']}。", "",
             "使用 Science 2022 配套源码中的 XDL 0.5.0、ChemputerXDL 1.0.0，源码原件保留且 SHA256 固定。Python 与运行时依赖版本在 native_platform.json，依赖由 requirements-platform.lock.txt 锁定。",
             "适配处理单一 Synthesis 外层 XDL 包装、带明确体积/RPM 单位的属性别名，并为省略 pid 的 Async 提供稳定且不冲突的 ID；显式 ID 和 Await 关系保持原样。未知质量不换算为体积，柱色谱细节不补造。适配副本、原始哈希与更改列表分别保留。", "",
             "编译开启内置 sanity checks，禁用交互。耗时估算所需控制器只允许 simulation=True，禁用网络、串口及真实控制器初始化；不执行实物实验。",
             "作者成功分区和仅翻译分区分开保存。编译通过不改变 human_review、benchmark_eligible 或完整化学可行性状态。", "",
             "通过记录：data/publications/platform_positives.jsonl；全部结果：data/publications/platform_validation.jsonl；编译文件：data/compiled/publication/。", "",
             "| 未通过程序 | 分区 | 阶段 | 原因 |", "|---|---|---|---|"]
    for row in rows:
        failure = row.get("failure")
        if failure:
            message = (failure["type"] + ": " + failure.get("message", "缺少唯一来源装置图")).replace("|", "/").replace("\n", " ")[:220]
            lines.append(f"| {row['id']} | {row['source_partition']} | {failure['stage']} | {message} |")
    (ROOT / "reports/native_platform.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _contrast_report():
    path = ROOT / "reports/hte_contrasts.json"
    if not path.exists():
        return
    summary = read_json(path)
    audit_path = ROOT / "reports/hte_contrasts_audit.json"
    audit = read_json(audit_path) if audit_path.exists() else {}
    rows = list(read_jsonl(ROOT / "data/hte/contrasts.jsonl"))
    lines = ["# HTE 实测单因素记录对照", "",
             f"对照 {summary['contrasts']:,} 组，涉及 {summary['experimental_runs']:,} 次原始实验、{summary['scaffold_groups']} 个产物骨架组。",
             f"上游原始记录与完整重复实验集合审计：{audit.get('passed', False)}。", "",
             "| 条件变量 | 对照组数 |", "|---|---:|"]
    lines.extend(f"| {risk} | {summary['per_risk'].get(risk, 0)} |" for risk in ("C1", "C2", "C3", "C4", "C6"))
    lines += ["", "同一研究、目标产物及分析方法相同，仅一个已记录因素不同。成功设置的全部重复实验须 >30%；失败设置的全部重复实验须 <5%。中间产率或重复分歧会取消该设置的资格。",
              "输入载体、加入顺序、非目标数量、器材、步骤说明和其他原始条件均保留在比较中。每组只选择一个确定的成功设置作为参照，不将所有成功/失败交叉组合扩增为独立实验。", "",
              "这些是实测条件对照，不是合成单故障样例。未记录因素仍可能混杂；C1 对照也未必满足合成算子的‘同类反应未见溶剂’前提。当前不授予 benchmark_eligible、gold 或任何 C 子类 judge 准入。", "",
              "完整记录见 `data/hte/contrasts.jsonl`，保留双方全部实验 ID、来源、原始 SHA256、测量产率、变化因素和条件摘要哈希。", "",
              "以下为每类最多 10 组原始证据示例；首个实验 ID 后的数量为该设置的重复次数。", "",
              "| 因素 | 成功实验 ID | 成功产率范围 % | 低产率实验 ID | 低产率范围 % |", "|---|---|---:|---|---:|"]
    shown = Counter()
    for row in rows:
        risk = row["risk_hypothesis"]
        if shown[risk] >= 10:
            continue
        shown[risk] += 1
        good, bad = row["success_observations"], row["failure_observations"]
        a, b = [r["yield_percent"] for r in good], [r["yield_percent"] for r in bad]
        lines.append(f"| {risk} | {good[0]['id']} ({len(good)}) | {min(a):.3f}–{max(a):.3f} | {bad[0]['id']} ({len(bad)}) | {min(b):.3f}–{max(b):.3f} |")
    (ROOT / "reports/hte_contrasts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _publication_report():
    path = ROOT / "reports/publication_candidates.json"
    if not path.exists():
        return
    data = read_json(path)
    audit_path = ROOT / "reports/publication_audit.json"
    audit = read_json(audit_path) if audit_path.exists() else {}
    lines = ["# 作者原始 XDL 参考语料", "",
             "来源：[Science 2022 作者数据包](https://zenodo.org/records/6534009)，DOI 10.5281/zenodo.6534009，CC BY 4.0。", "",
             f"- XML 与声明引用检查通过、去重后的程序：{data['static_valid_unique_xdl']}。",
             f"- 作者分区：{data['source_partitions']}。成功分区是作者报告，翻译分区不视为实测成功。",
             f"- 机械修复：{data['mechanically_repaired']}；待平台或人工确认：{data['quarantined']}。",
             f"- 文件校验与补丁复原审计：{audit.get('passed', False)}。严格 gold：0。", "",
             "原始 .xdl、装置图和作者编译文件在 data/upstream/chemputer_2022/；可检查的副本在 data/xdl/publication/。",
             "修复仅涉及成对 XML 标签的大小写和能唯一匹配已声明名称的尾随空格，原始文件不变。每份副本有来源 SHA256、结果 SHA256、修复记录和 RFC 6902 差异。", "",
             "这是独立参考语料，没有混入 ORD 正样本计数，也没有自动授予 benchmark_eligible 或 gold。静态检查不能证明全部化学步骤、预装物料、器材约束和实机执行均已确认。",
             "部分作者程序从手工预装物料后的阶段开始；必须结合原文与装置记录检查流程范围。",
             "通过 HTTP Range 只下载所需成员；ZIP CRC32 与成员 SHA256 已记录，未声称验证未完整下载的 ZIP 总校验和。"]
    (ROOT / "reports/publication_corpus.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _judge_report():
    path = ROOT / "reports/jev_metrics.json"
    if not path.exists():
        (ROOT / "reports/judge_report.md").write_text("# Judge 准入报告\n\n尚未训练或评估。未准入。\n", encoding="utf-8")
        return
    data = read_json(path)
    m = data["test_metrics"]
    lines = ["# Judge 准入报告", "", "当前模型未准入，不能作为 Jev-as-judge。", "",
             f"HTE 真实观测 {data['observations']:,} 条，其中 <5% 低产率 {data['measured_failures']:,} 条；按 {data['scaffold_groups']} 个产物骨架分组。",
             f"划分：{data['split']}；骨架交叉泄漏：{data['scaffold_leakage']}。验证集单独做 Platt 校准。", "",
             f"通用低产率基线测试：AUROC={m['auroc']:.4f}；ECE={m['ece']:.4f}；p≥0.9 数量={m['high_confidence_count']}；precision={m['precision_at_p_ge_0_9']}。",
             "这些是通用低产率预测指标，不能当作 C 子类指标。", "",
             "| 子类 | 是否准入 | 原因 |", "|---|---|---|"]
    lines.extend(f"| {risk} | 否 | 缺少该子类的因果归因与独立校准标签 |" for risk in data["per_risk"])
    lines += ["", "![校准曲线](hte_reliability.png)", "", "## 测试中误差最大的 20 条", "",
              "| ORD ID | 实测产率 % | 预测低产率概率 |", "|---|---:|---:|"]
    lines.extend(f"| {r['id']} | {r['yield_percent']:.3f} | {r['p_low_yield']:.4f} |" for r in data["failure_cases"])
    (ROOT / "reports/judge_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _coverage_plot(stats, risks):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    x = np.arange(len(risks))
    fig, ax = plt.subplots(figsize=(11, 4), layout="constrained")
    ax.bar(x - 0.18, [stats["observed_risk_counts"].get(r, 0) for r in risks], 0.36, color="#245c7a", label="Source-derived research candidates")
    ax.bar(x - 0.18, [stats.get("instantiated_sop_risk_counts", {}).get(r, 0) for r in risks], 0.36,
           bottom=[stats["observed_risk_counts"].get(r, 0) for r in risks], color="#c69048", label="Instantiated SOP scenarios")
    ax.bar(x + 0.18, [stats["control_risk_counts"].get(r, 0) for r in risks], 0.36, color="#c6cbd0", label="Authored controls (separate)")
    ax.axhline(10, ls="--", color="#b66c2c", lw=1, label="Requested 10 per category")
    ax.set(xticks=x, xticklabels=risks, ylabel="Number of examples", ylim=(0, max(stats["control_risk_counts"].values()) + 5))
    ax.legend(frameon=False, ncols=2, fontsize=8)
    fig.savefig(ROOT / "reports/risk_coverage.png", dpi=180)
    plt.close(fig)
