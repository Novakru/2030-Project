"""Read-only review cues derived from existing evidence, never new risk decisions."""
import json
import re
import xml.etree.ElementTree as ET

from audit.records import as_dict, field, list_values, quality, risk_codes

RISK_NAMES = {
    "A1": "容量或装填率越界", "A2": "温控越界", "A3": "转速或流速越界",
    "A4": "材质不兼容", "A5": "硬件拓扑缺件", "B1": "开放体系超沸点",
    "B2": "低于凝固点", "B3": "点火或自燃边界", "B4": "不相容试剂对",
    "B5": "加料顺序放热", "C1": "溶剂条件扰动", "C2": "温度条件扰动",
    "C3": "试剂或催化剂扰动", "C4": "计量条件扰动", "C5": "敏感体系气氛缺失",
    "C6": "时间条件扰动", "D1": "步骤依赖顺序错误", "D2": "关键步骤缺失",
    "D3": "引用未声明", "D4": "单位维度错误",
}
ACTION_NAMES = {"Add": "加料", "AddSolid": "加入固体", "Stir": "搅拌", "StopStir": "停止搅拌",
                "HeatChill": "控温", "HeatChillToTemp": "调整温度", "Atmosphere": "气氛",
                "Evaporate": "蒸发", "Transfer": "转移", "Separate": "分液", "RunColumn": "过柱",
                "Repeat": "循环", "Wait": "等待", "Filter": "过滤", "Dry": "干燥"}
FIELD_NAMES = {"amount": "用量", "value": "数值", "unit": "单位", "temp_C": "温度 (°C)",
               "controller_setpoint_C": "控制器设定 (°C)", "duration_s": "时间 (s)",
               "rpm": "转速 (rpm)", "reagent": "原料引用", "name": "名称", "smiles": "SMILES",
               "chemical": "化学品", "capacity_mL": "容量 (mL)", "volume_mL": "体积 (mL)",
               "pressure_control": "压力控制", "reflux": "回流", "atmosphere": "气氛",
               "max_C": "温度上限 (°C)", "min_C": "温度下限 (°C)", "setpoint_C": "设定温度 (°C)",
               "bp_C": "沸点 (°C)", "mp_C": "熔点 (°C)", "flash_C": "闪点 (°C)",
               "material": "接液材质", "solvent": "溶剂", "controller": "控制器",
               "references": "未声明引用", "permitted": "允许单位", "dependency": "前置步骤"}
REASONS = {"no_adjacent_quantity": "原文别名附近缺少可独立比对的用量",
           "sample_to_controller_temperature_mapping_unknown": "样品温度与控制器设定温度的对应关系未确定",
           "solution_freezing_point_not_established": "溶液凝固点尚未确定",
           "hardware_human_verification_pending": "器材参数尚待人工核验",
           "manual_protocol_review_pending": "流程尚待人工核对", "protocol_review_pending": "流程尚待人工核对"}
MISSING = "未提供"


def text(value, limit=260):
    if value is None:
        result = "空值"
    elif isinstance(value, bool):
        result = "是" if value else "否"
    elif isinstance(value, dict) and "value" in value and "unit" in value:
        result = f"{value['value']} {value['unit']}"
    elif isinstance(value, (dict, list)):
        result = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        result = str(value)
    return result if len(result) <= limit else result[:limit] + "…"


def risk_name(code):
    return f"{code} · {RISK_NAMES.get(code, code)}"


def hardware_node_summary(node, node_id):
    if not isinstance(node, dict):
        return text(node)
    category = {"heater_stirrer": "加热搅拌器", "heater": "加热设备", "stirrer": "搅拌设备",
                "vessel": "容器", "pump": "泵", "column": "色谱柱"}.get(node.get("category"), "器材")
    model = node.get("id")
    return f"{category} {node_id}" + (f"（{model}）" if model else "")


def pointer(record, path):
    try:
        value = record
        for key in path.lstrip("/").split("/"):
            key = key.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        return MISSING


def procedure(record):
    """Normalize display only. XML paths remain locators, not execution semantics."""
    steps = field(record, "steps", [])
    if isinstance(steps, list) and steps:
        return [dict(s, _number=i + 1, _id=str(s.get("step_id", s.get("id", i + 1))))
                for i, s in enumerate(steps) if isinstance(s, dict)]
    xdl = field(record, "xdl")
    if not isinstance(xdl, str):
        return []
    try:
        root = ET.fromstring(xdl)
    except ET.ParseError:
        return []
    output = []
    def visit(element, path):
        counts = {}
        for child in element:
            counts[child.tag] = counts.get(child.tag, 0) + 1
            child_path = f"{path}/{child.tag}[{counts[child.tag]}]"
            output.append(dict(child.attrib, op=child.tag, _id=child_path, _number=len(output) + 1))
            visit(child, child_path)
    for part in root.iter("Procedure"):
        visit(part, "/Synthesis/Procedure")
    return output


def _locators(values, steps):
    ids = []
    if values.get("step_id") is not None:
        ids.append(str(values["step_id"]))
    index = values.get("step")
    # This dataset's evidence stores zero-based step offsets; IDs take precedence.
    if not ids and isinstance(index, int) and 0 <= index < len(steps):
        ids.append(steps[index]["_id"])
    return ids


def _step_ids(path, record, parent, operation, evidence):
    steps = procedure(record)
    parts = path.strip("/").split("/")
    ids = []
    if len(parts) > 1 and parts[0] == "steps" and parts[1].isdigit():
        index = int(parts[1])
        sequence = procedure(parent or {}) if operation == "remove" and len(parts) == 2 else steps
        if index < len(sequence):
            ids.append(sequence[index]["_id"])
    if len(parts) > 1 and parts[0] == "reagents" and parts[1].isdigit():
        reagents = [pointer(field(r, "reagents", []), "/" + parts[1]) for r in (record, parent or {})]
        reagent_ids = {str(r["id"]) for r in reagents if isinstance(r, dict) and "id" in r}
        ids.extend(s["_id"] for s in steps if str(s.get("reagent")) in reagent_ids)
    if not ids:
        for entry in evidence:
            ids.extend(_locators(as_dict(entry.get("values")), steps))
    elif operation == "move":
        for entry in evidence:
            ids.extend(_locators(as_dict(entry.get("values")), steps))
    return list(dict.fromkeys(ids))


def review_points(record, parent=None):
    """Prioritize semantic edits, failed checks and unknowns; keep bookkeeping folded."""
    steps = procedure(record)
    codes = risk_codes(record)
    label = as_dict(record.get("label"))
    evidence_value = label.get("evidence")
    evidence = [e for e in list_values(evidence_value) if isinstance(e, dict)]
    groups = {}
    for change in list_values(record.get("diff")):
        if not isinstance(change, dict):
            continue
        path = str(change.get("path", ""))
        parts = path.strip("/").split("/")
        if parts[0] not in ("steps", "reagents", "hardware", "context"):
            continue
        prefix = "/" + "/".join(parts[:3] if parts[0] == "hardware" else parts[:2])
        point = groups.setdefault(prefix, {"key": prefix, "title": "", "step_ids": [], "changes": [],
                                            "evidence": evidence, "note": "核对改动是否与风险标签一致。"})
        op = change.get("op")
        base = field(parent, parts[0]) if parent else None
        relative = "/" + "/".join(parts[1:])
        quantity = len(parts) > 2 and parts[-2] == "amount"
        if quantity:
            relative = "/" + "/".join(parts[1:-1])
        before = pointer(base, relative) if parent else "父记录未导入"
        after = pointer(field(record, parts[0]), relative)
        if op == "remove":
            after = "已移除"
        if op == "move":
            before, after = change.get("from", MISSING), path
        point["changes"].append({"field": "用量" if quantity else FIELD_NAMES.get(parts[-1], parts[-1]),
                                  "before": text(before), "after": text(after), "path": path})
        if op == "remove" and parts[0] == "steps" and len(parts) == 2:
            point["removed"] = True
            sequence = procedure(parent or {})
            if parts[1].isdigit() and int(parts[1]) < len(sequence):
                point["removed_step"] = sequence[int(parts[1])]
        point["step_ids"] += _step_ids(path, record, parent, op, evidence)
        point["step_ids"] = list(dict.fromkeys(point["step_ids"]))
        section = {"steps": "步骤", "reagents": "原料", "hardware": "器材", "context": "体系条件"}[parts[0]]
        number = f" {int(parts[1]) + 1}" if len(parts) > 1 and parts[1].isdigit() else ""
        point["title"] = f"{section}{number} · {'删除' if op == 'remove' else '顺序改变' if op == 'move' else '改动核对'}"
        if parts[:2] == ["hardware", "nodes"] and len(parts) == 3:
            node_id = parts[2]
            point["changes"][-1]["field"] = "设备清单中的 " + node_id
            point["changes"][-1]["before"] = hardware_node_summary(before, node_id)
            point["changes"][-1]["after"] = "设备已删除" if op == "remove" else hardware_node_summary(after, node_id)
            point["title"] = f"器材 · {'删除' if op == 'remove' else '改动'} {node_id}"
            # Show the explicit heat request before the engine's generic Stir dependency.
            preferred = next((s for s in steps if s["_id"] in point["step_ids"] and
                              s.get("op") in ("HeatChill", "HeatChillToTemp") and
                              (s.get("temp_C") is not None or s.get("temp") is not None)), None)
            if preferred and "A5" in codes:
                point["preferred_step_id"] = preferred["_id"]
    points = list(groups.values())
    cross = as_dict(field(record, "crosscheck"))
    for index, check in enumerate(list_values(cross.get("quantity_checks"))):
        if not isinstance(check, dict):
            continue
        status = check.get("status")
        measurements = list_values(check.get("measurements"))
        quotes = [m.get("quote", m) if isinstance(m, dict) else m for m in measurements]
        points.append({"key": f"quantity:{index}", "title": f"用量 · {check.get('alias', check.get('reagent', index + 1))}",
                       "step_ids": _locators(check, steps), "changes": [{"field": "用量",
                           "before": "；".join(text(q) for q in quotes) or "无独立原文用量",
                           "after": text(check.get("expected", MISSING)), "path": ""}],
                       "note": "自动核对匹配，仍需确认来源与单位。" if status == "matched" else
                               REASONS.get(check.get("basis"), "用量未完成独立核对，请人工确认。"),
                       "evidence": [check], "priority": 2 if status == "matched" else 0})
    for index, unknown in enumerate(list_values(quality(record).get("unknown_constraints"))):
        item = as_dict(unknown)
        points.append({"key": f"unknown:{index}", "title": risk_name(str(item.get("rule", "约束"))),
                       "step_ids": _locators(item, steps), "changes": [], "evidence": [unknown],
                       "note": REASONS.get(item.get("reason"), text(unknown)), "priority": 1})
    for index, finding in enumerate(list_values(as_dict(field(record, "mosaic")).get("findings"))):
        if not isinstance(finding, dict):
            continue
        quote = finding.get("quote", "")
        located = [s["_id"] for s in steps if quote and (quote in as_dict(s.get("meta")).get("evidence", "")
                   or as_dict(s.get("meta")).get("evidence") and as_dict(s.get("meta"))["evidence"] in quote)]
        represented = any(quote and quote == as_dict(event).get("evidence")
                          for event in list_values(as_dict(field(record, "context")).get("source_context_events")))
        note = ("程序已将此项原文映射为器材或上下文，请核对映射：" if represented else
                "模型建议，尚未构成已证实风险：") + str(finding.get("message", ""))
        points.append({"key": f"model-finding:{index}", "title": "模型核对建议 · " + str(finding.get("code", "来源一致性")),
                       "step_ids": located, "changes": [{"field": "原文", "before": quote, "after": "待专家核对", "path": ""}],
                       "evidence": [finding], "note": note,
                       "priority": -1 if finding.get("severity") == "error" and not represented else 1})
    for category in ("conflicts", "missing"):
        for index, value in enumerate(list_values(cross.get(category))):
            points.insert(0, {"key": f"{category}:{index}", "title": "核对冲突" if category == "conflicts" else "缺失信息",
                             "step_ids": _locators(as_dict(value), steps), "changes": [],
                             "evidence": [value], "note": text(value), "priority": -1})
    if not points:
        contract = as_dict(record.get("contract"))
        ids = [contract["consumer_xpath"]] if contract.get("consumer_xpath") else []
        if not ids:
            ids = [step for e in evidence for step in _locators(as_dict(e.get("values")), steps)]
        points.append({"key": "overview", "title": risk_name(codes[0]) if codes else "流程与来源核对",
                       "step_ids": ids, "changes": [], "evidence": evidence or [contract or label],
                       "note": "核对关键输入步骤是否缺失，及后续步骤的物料来源。" if contract else
                               "核对流程、原始证据及记录标签。", "contract": contract})
    return sorted(points, key=lambda p: p.get("priority", -2))


def mechanism_name(identifier):
    names = {"A1.single_add_overfill": "单次加料超容", "A1.cumulative_overfill": "累计加料超容",
             "A1.active_fill_fraction": "搅拌或控温时装填率过高",
             "A5.missing_controller": "移除控温或搅拌设备", "A5.incompatible_bound_capability": "控制器绑定到不具备该功能的器材",
             "A5.unresolved_binding": "控制器绑定引用不存在", "A5.disconnected_path": "切断物料转移路径",
             "B1.overheat_open_liquid": "提高开放体系的温度至常压沸点以上",
             "B1.open_hot_closed_vessel": "将高于常压沸点的封闭体系改为开放",
             "C2.cooler_than_source": "降低反应温度", "C2.hotter_than_source": "提高反应温度",
             "C3.catalyst_omission": "省略催化剂加料", "C3.catalyst_identity_substitution": "催化剂位置换成其他物料",
             "D3.undefined_vessel": "引用未声明的容器", "D3.undefined_reagent": "引用未声明的试剂",
             "D4.nonpositive_quantity": "将用量改为无效数值", "D4.incompatible_dimension": "将用量改成不相容的量纲",
             "D2.omitted_transfer": "删除唯一物料转入步骤", "D2.omitted_filterthrough": "删除唯一滤过转入步骤"}
    if identifier in names:
        return names[identifier]
    if identifier.startswith("C4."):
        return "降低指定组分投料量" if ".depleted_" in identifier else "提高指定组分投料量"
    if identifier.startswith("C6."):
        return "延长原有操作时长" if ".extended_" in identifier else "缩短原有操作时长"
    return identifier


def focus_indices(steps, point):
    ids = point.get("step_ids", [])
    canonical = lambda value: str(value).replace("[1]", "")
    found = [i for i, step in enumerate(steps) if any(canonical(step["_id"]) == canonical(v) for v in ids)]
    if not found:
        match = re.match(r"/steps/(\d+)", point["key"])
        index = min(int(match[1]), len(steps) - 1) if match and steps else 0
        found = [index] if steps else []
    preferred = point.get("preferred_step_id")
    if preferred:
        found.sort(key=lambda i: steps[i]["_id"] != preferred)
    return found


def step_summary(step, record):
    op = str(step.get("op", step.get("action", step.get("type", "步骤"))))
    title = ACTION_NAMES.get(op, op)
    reagent = step.get("reagent")
    reagents = field(record, "reagents", [])
    item = next((r for r in reagents if isinstance(r, dict) and r.get("id") == reagent), {}) if isinstance(reagents, list) else {}
    reagent_name = item.get("name", reagent)
    if not reagent_name or reagent_name == item.get("smiles"):
        reagent_name = as_dict(step.get("meta")).get("source_alias") or reagent_name
    pieces = [str(reagent_name)] if reagent_name else []
    for key in ("amount", "volume", "mass"):
        if key in step:
            pieces.append(text(step[key]))
    for key, unit in (("temp_C", "°C"), ("controller_setpoint_C", "°C · 控制器"), ("duration_s", "s"), ("rpm", "rpm")):
        if step.get(key) is not None:
            pieces.append(f"{step[key]} {unit}")
    for key in ("temp", "time", "gas", "from_vessel", "to_vessel", "repeats"):
        if key in step:
            pieces.append(f"{key}: {step[key]}")
    return title, " · ".join(pieces)
