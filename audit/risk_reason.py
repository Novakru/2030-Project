"""Explain existing labels from their frozen evidence; do not evaluate or relabel chemistry."""
from audit.records import as_dict, field, list_values
from audit.review_view import hardware_node_summary, procedure, text

# These are descriptions of the project's existing rules, not new safety decisions.
# Conditions mirror symbolic.py, mutation_rules.py and native material contracts.
RULES = {
    "A1.capacity": (
        "规则记录的液体体积为 {volume_mL} mL，容器声明容量为 {capacity_mL} mL；原标注据此提出容量越界。",
        "触发条件：规则跟踪的累计液体体积大于声明容量。",
        "核对体积累计、容器绑定和容量来源是否正确。"),
    "A1.fill_fraction": (
        "规则记录的液体体积为 {volume_mL} mL，容器容量为 {capacity_mL} mL；原标注使用装填率规则。",
        "本项目该规则的触发条件：搅拌或控温时，体积超过声明容量的 2/3。",
        "2/3 是本项目规则的阈值，需核对其对该器材与操作是否适用。"),
    "A1.destination_capacity": (
        "转移后的目标容器液体体积记录为 {volume_mL} mL，声明容量为 {capacity_mL} mL。",
        "触发条件：转移后目标容器体积超过容量。", "核对转入量、原有物料及目标容器。"),
    "A1.syringe_capacity": (
        "单次转移量记录为 {amount}，注射器容量为 {syringe_capacity_mL} mL。",
        "触发条件：单次转移量超过注射器容量，且没有声明分次转移。", "核对单位及分次转移配置。"),
    "A2.temperature_range": (
        "控制器设定温度记录为 {setpoint_C} °C，设备下限为 {min_C} °C、上限为 {max_C} °C。",
        "触发条件：控制器设定值低于已知下限或高于已知上限。",
        "核对参数是否属于该控制器；样品温度不能直接当作加热板设定温度。"),
    "A3.stirring_range": (
        "搅拌转速记录为 {rpm} rpm，声明范围为 {min}～{max} rpm。",
        "触发条件：转速低于已知下限或高于已知上限。", "核对实际设备、转速单位和参数范围。"),
    "A4.material_incompatible": (
        "原规则将化学品 {chemical} 与接液材质 {material} 的接触标为不兼容。",
        "触发条件：接触组合命中已有材质兼容性条目。", "核对化学品识别、浓度、实际接液部件及来源条目的适用范围。"),
    "A5.required_controller_missing": (
        "原规则在该操作中需要控制器 {controller}，但未在声明的器材节点中找到它。",
        "触发条件：操作要求的控制器节点缺失。", "核对器材绑定及节点命名，排除别名或图转换造成的缺失。"),
    "A5.required_component_missing": (
        "原规则记录缺少操作所需组件 {component}。",
        "触发条件：所需组件未在器材图中声明。", "核对组件是否真实缺失，或仅名称不同。"),
    "A5.controller_capability_mismatch": (
        "步骤请求 {operation}，控制器却绑定到 {controller}；该节点的器材类型记录为 {category}。",
        "触发条件：绑定对象属于已知的非控温/搅拌器材类型，无法按该角色承接操作。",
        "核对绑定是否指错节点、器材类型是否准确，以及是否存在独立的加热或搅拌装置。"),
    "A5.disconnected_path": (
        "原规则未找到从 {from} 到 {to} 的声明连通路径。",
        "触发条件：转移所需路径在器材图中不可达。", "核对器材图、连接方向和转移绑定。"),
    "B1.open_above_bp": (
        "溶剂记录为 {solvent}，温度为 {temp_C} °C，所用常压沸点为 {bp_C} °C。",
        "触发条件：开放或常压体系、未声明回流，且温度高于所用常压沸点。",
        "核对压力、回流、溶剂组成及沸点数据的适用条件。"),
    "B2.pure_solvent_below_mp": (
        "溶剂记录为 {solvent}，温度为 {temp_C} °C，所用熔点为 {mp_C} °C。",
        "触发条件：明确的纯溶剂场景，且温度低于所用熔点。",
        "核对纯物质与平衡假设；混合物或溶液不能直接套用单组分熔点。"),
    "B3.ignition_exposure": (
        "溶剂记录为 {solvent}，温度为 {temp_C} °C，所用闪点为 {flash_C} °C。",
        "触发条件：存在点火源及蒸气暴露，且温度高于所用闪点。",
        "核对点火源和蒸气暴露是否真实存在；仅高于闪点不足以支持此条标注。"),
    "B3.autoignition_boundary": (
        "溶剂记录为 {solvent}，温度为 {temp_C} °C，所用自燃温度为 {ait_C} °C。",
        "触发条件：声明有氧环境，且温度达到或超过所用自燃温度。", "核对环境、物性来源及自燃温度的适用条件。"),
    "B4.carboxylic_acid_cyanide": (
        "原规则识别到共存的反应性基团组合 {pair}，并将其与已有不相容条目匹配。",
        "触发条件：基团组合命中已有反应性规则，并满足该规则的接触或液体存量条件。",
        "核对结构推断的基团是否正确、是否实际接触，以及规则是否适用于该体系。"),
    "B4.incompatible_contact": (
        "原规则将组分组合 {pair} 的接触标为不相容。",
        "触发条件：同一容器中的组分命中已有不相容组合。", "核对实际接触、浓度和来源适用范围。"),
    "B5.water_into_concentrated_acid": (
        "原规则在浓硫酸稀释场景中，将此步识别为向已存在的浓酸体系加水，因而标记加料顺序风险。",
        "触发条件：稀释目的明确，先有浓硫酸、此前没有水，随后加入水。",
        "核对实际顺序和浓酸条件，不能仅因酸和水共存就判定此风险。"),
    "C5.source_declared_oxygen_sensitive": (
        "来源标明体系对氧敏感；原规则在该步之前未识别到步骤级的惰性气氛建立记录。",
        "触发条件：来源要求惰性保护，而当前步骤级气氛状态不满足要求。",
        "核对源文本、手套箱及气氛上下文，排除气氛继承或步骤表示造成的误判。"),
    "C5.inert_context_missing": (
        "原规则将试剂 {reagent} 识别为空气敏感，但在加入时未识别到所需惰性环境。",
        "触发条件：已有敏感性标注与加入时的惰性状态不匹配。", "核对敏感性来源及实际保护条件。"),
    "D1.order_dependency": (
        "原规则记录本步依赖前置步骤 {dependency}，但处理到本步时，该前置步骤尚未出现。",
        "触发条件：明确依赖的步骤在当前步骤之前尚未完成。", "核对依赖关系及调序后步骤 ID 是否保持正确。"),
    "D3.undeclared_reference": (
        "此步引用了 {references}，原规则未在相应试剂表或器材节点中找到声明。",
        "触发条件：步骤引用的对象未声明。", "核对 ID、别名及声明是否遗漏。"),
    "D4.quantity_dimension": (
        "该步用量记录为 {amount}，该操作允许的单位为 {permitted}。",
        "触发条件：用量单位不属于该操作允许的量纲。", "核对量纲和字段含义；mL 与 L 的纯倍率错误不属于此条规则。"),
    "D4.nonpositive_quantity": (
        "该步用量记录为 {amount}，原规则将其识别为无效数值。",
        "触发条件：用量不是数值或不大于零。", "核对缺失值、零用量与源文本的实际含义。"),
}

SOFT = {
    "C1": "溶剂由 {original} 替换为 {replacement}；已有证据将其描述为不同溶剂类别的条件扰动。",
    "C2": "类别参考温度的 1%～99% 分位为 {q01_C}～{q99_C} °C；构造记录使用相对下分位的偏移 {shift_C} °C。",
    "C3": "构造记录移除了催化剂加料 {removed_catalyst}；原标注据此提出催化剂条件扰动假设。",
    "C4": "原用量为 {original}，构造缩放因子为 {amount_scale}；原标注据此提出计量条件扰动假设。",
    "C6": "类别参考时长的 1% 分位为 {q01_seconds} s；构造记录使用相对该下分位的因子 {factor}。",
}


class EvidenceValues(dict):
    def __missing__(self, key):
        return "未提供"


def _duration(seconds):
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        if seconds >= 3600 and seconds % 3600 == 0:
            return f"{seconds / 3600:g} 小时"
        if seconds >= 60 and seconds % 60 == 0:
            return f"{seconds / 60:g} 分钟"
    return f"{text(seconds)} 秒"


def soft_change_summary(record, parent=None):
    intervention = as_dict(as_dict(record.get("mutation")).get("intervention"))
    identifier = intervention.get("step_id")
    if intervention.get("kind") == "step_parameter" and identifier:
        current = next((s for s in procedure(record) if s["_id"] == identifier), {})
        original = next((s for s in procedure(parent or {}) if s["_id"] == identifier), {})
        path = str(intervention.get("field", "")).strip("/").split("/")
        def value(step):
            result = step
            for key in path:
                result = as_dict(result).get(key)
            return "未提供" if result is None else text(result)
        name = {"temp_C": "温度（°C）", "duration_s": "时长（秒）", "amount": "加料用量"}.get(path[0], path[0])
        return f"步骤 {identifier} 的{name}由 {value(original)} 改为 {value(current)}；该条件变化仍是待核验的扰动假设。"
    if intervention.get("kind") == "reagent_identity":
        identifier = intervention.get("reagent_id")
        def name(row):
            entries = field(row, "reagents", [])
            return next((str(r.get("name", identifier)) for r in entries if isinstance(r, dict) and r.get("id") == identifier), "未提供")
        return f"试剂 {identifier} 由 {name(parent or {})} 替换为 {name(record)}；记录未观察到此替换后的实验结果。"
    return None


def controller_dependency(record, entry, entries, parent=None):
    controller = as_dict(entry.get("values")).get("controller")
    if not isinstance(controller, str):
        return None
    hardware = as_dict(field(record, "hardware"))
    nodes = as_dict(hardware.get("nodes"))
    parent_nodes = as_dict(as_dict(field(parent or {}, "hardware")).get("nodes"))
    ids = {as_dict(e.get("values")).get("step_id") for e in entries
           if e.get("rule_id") == "A5.required_controller_missing" and
           as_dict(e.get("values")).get("controller") == controller}
    affected = []
    for step in procedure(record):
        if step["_id"] not in ids:
            continue
        op = step.get("op")
        duration = _duration(step["duration_s"]) if step.get("duration_s") is not None else None
        if op in ("HeatChill", "HeatChillToTemp"):
            temperature = f"{step['temp_C']} °C" if step.get("temp_C") is not None else text(step.get("temp", "未提供"))
            request = f"保持 {temperature}"
            if step.get("stir") in (True, "true", "True"):
                request += " 并搅拌"
            if duration:
                request += f" {duration}"
        elif op == "Stir":
            request = "搅拌" + (f" {duration}" if duration else "")
        else:
            request = str(op or "原操作")
        affected.append({"step_id": step["_id"], "number": step["_number"], "op": op, "request": request})
    affected.sort(key=lambda step: step["op"] not in ("HeatChill", "HeatChillToTemp"))
    present = controller in nodes and nodes[controller] is not None
    existed = controller in parent_nodes and parent_nodes[controller] is not None
    device = hardware_node_summary(parent_nodes[controller], controller) if existed else f"控制器 {controller}"
    if present:
        summary = f"原标注声称缺少 {controller}，但当前设备清单仍包含此节点；需要核对原标注与实际绑定是否一致。"
    else:
        summary = f"与父记录相比，{device}已从设备清单删除。" if existed else f"当前设备清单没有声明{device}。"
        if affected:
            first = affected[0]
            summary += f"第 {first['number']} 步（{first['step_id']}）仍要求{first['request']}，但该设备节点已不存在。"
    retained = controller in as_dict(hardware.get("bindings")).values()
    if retained and not present:
        summary += f"配置中的 {controller} 绑定只是仍未清除的引用，并不代表设备仍在清单中。"
    return {"summary": summary, "affected_steps": affected, "missing_controller": controller,
            "device_present": present, "parent_device_present": existed, "binding_retained": retained,
            "review_hint": "本项目把 Stir 和 HeatChill 都关联到 heater。请分别核对加热和搅拌所需设备，"
                           "以及是否有其他设备可承接操作；室温搅拌触发此规则依赖这一绑定假设。"}


def explain_risk(record, point=None, parent=None):
    """Return text plus original provenance. None means there is no risk label to explain."""
    label = as_dict(record.get("label"))
    code = label.get("risk_l2")
    if not isinstance(code, str) or not code:
        return None
    evidence = label.get("evidence")
    entries = [e for e in list_values(evidence) if isinstance(e, dict)]
    matching = [e for e in entries if str(e.get("rule_id", "")).startswith(code + ".") or e.get("risk") == code]
    candidates = matching or entries
    ids = (point or {}).get("step_ids", [])
    preferred = (point or {}).get("preferred_step_id") or (ids[0] if ids else None)
    entry = next((e for e in candidates if preferred and as_dict(e.get("values")).get("step_id") == preferred), None)
    if entry is None:
        entry = next((e for e in candidates if as_dict(e.get("values")).get("step_id") in ids),
                     candidates[0] if candidates else {})
    result = {"risk": code, "rule_id": entry.get("rule_id"), "label_type": label.get("label_type"),
              "judge": label.get("judge"), "scope": label.get("scope"), "source_url": entry.get("source_url"),
              "origin": "结构化证据解释", "available": True,
              "raw_evidence": evidence, "selected_evidence": entry, "contract": record.get("contract")}
    original = next((v for v in (label.get("reason"), label.get("rationale"), entry.get("reason"), entry.get("rationale"))
                     if isinstance(v, str) and v.strip()), None)
    if original:
        result.update(summary=original, origin="原始原因文字", condition="以原始证据和适用范围核对。",
                      review_hint="此处保留原文原因，不代表专家已经认可。")
        return result
    values = EvidenceValues({k: text(v) if v is not None else "未提供" for k, v in as_dict(entry.get("values")).items()})
    rule = RULES.get(result["rule_id"])
    if rule:
        result.update(summary=rule[0].format_map(values), condition=rule[1], review_hint=rule[2])
        context = as_dict(field(record, "context"))
        context_keys = {"B1": ("pressure_control", "reflux"), "B2": ("pure_solvent",),
                        "B3": ("ignition_source", "vapor_exposed", "oxygen_present")}.get(code, ())
        result["context"] = {k: context.get(k, "未提供") for k in context_keys}
        if result["rule_id"] == "A5.required_controller_missing":
            details = controller_dependency(record, entry, candidates, parent)
            if details:
                result.update(details)
    elif label.get("label_type") == "soft" and code in SOFT:
        soft_values = EvidenceValues({k: text(v) if v is not None else "未提供" for k, v in as_dict(evidence).items()})
        result.update(summary=soft_change_summary(record, parent) or SOFT[code].format_map(soft_values),
                      condition="条件扰动假设，不能据此当作已观察到的实验失败或确定因果。",
                      review_hint="核对扰动、参考分位或原值是否正确，以及该假设是否有独立证据。",
                      calibrated=label.get("calibrated"))
    elif code == "D2" and as_dict(record.get("contract")):
        contract = as_dict(record["contract"])
        complete = (contract.get("initial_volume") == 0 and bool(contract.get("basis"))
                    and bool(contract.get("producer_xpath")) and bool(contract.get("consumer_xpath"))
                    and as_dict(record.get("mutation")).get("operation") == "remove_statement")
        summary = (f"原物料约束声明容器 {text(contract.get('vessel', '未提供'))} 初始体积为 0；"
                   "蒸发前的唯一输入步骤被移除，后续蒸发仍保留。") if complete else (
                   "该记录给出了物料输入依赖约束，但初始状态或删步依据未完整提供；需核对后续操作的输入是否缺失。")
        result.update(summary=summary,
                      condition="触发条件：原图声明为空容器，且被移除步骤是该后续操作之前唯一的物料输入。",
                      review_hint="核对原图和唯一输入假设；此判定只覆盖物料依赖，不认证其他化学或硬件约束。",
                      origin="原生物料依赖约束解释")
    else:
        result.update(summary="该记录没有可直接展示的风险原因文字，也没有匹配的证据解释模板。",
                      condition="请依据原始证据核对；此处不自动补写因果。",
                      review_hint="可在审核意见中指出原因缺失或不支持该风险标签。", available=False)
    return result
