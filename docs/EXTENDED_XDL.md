# 可自动扩展的流程语言

默认领域为 `chemistry.extended/1`，输出 profile 为 `mosaic-xdl/1`。目标是完整表示实验原文；未报告的参数采用明确标识。原子操作是否已有设备执行实现另行记录，不限制它进入表示库。

初次提取、独立复核和器材映射仍仅使用文本。操作补充 agent 接收原文、已有步骤、未表示动作和操作合同，优先复用；需要新语义时输出声明式合同和实例。名称、参数类型、状态作用、器材角色与逐字段原文证据一并保存。原有步骤分类若不准确，可由更合适的新操作表达，但已知数量、身份、条件与顺序不能丢失。模型不生成执行代码。

例如，原文 “The solid was dried under vacuum.” 可以生成新的 `Dry`，实例为：

```json
{
  "op": "Dry",
  "parameters": {
    "condition": {"value": "vacuum", "evidence": "The solid was dried under vacuum."},
    "duration_s": {
      "status": "not_reported", "marker": "__NOT_REPORTED__",
      "raw": null, "evidence": "The solid was dried under vacuum."
    }
  }
}
```

合同和实例检查通过后，自动进入 `library_registry.json` 的 `extension_operations`，状态为 `representation_status=admitted`、`execution_supported=false`。相同完整合同合并来源证据；不同合同版本保留语义摘要，避免把干燥有机相与烘干固体误合并。`--registry` 可将该库用于下一批提取。尚未证明通用最小集。

## 缺失参数

| 状态 | 标识 | 含义 |
|---|---|---|
| not_reported | `__NOT_REPORTED__` | 原文没有提供该参数 |
| qualitative | `__QUALITATIVE__` | 只有定性描述，如 overnight、room temperature；保留原词 |
| ambiguous | `__AMBIGUOUS__` | 存在范围、歧义或多个候选值；保留原词 |

核心步骤的未知值放在 `step.missing_parameters`，数值字段保持缺席；新操作在自己的参数对象中保存标识。XML 完整保存这些对象。已报告数字不能伪装成未报告，已知用量仍有试剂邻接和单位检查。同一加料的质量、物质的量等多个读数可同时保留在 `source_quantities`。

质量字段分别记录 `representation_complete`、`parameters_complete`、`execution_ready`。动作均已表达、缺失参数已标记的记录可以是正常 silver 正例。缺参使对应风险规则返回 unknown；没有状态解释器的新操作也传播未知，不当作空操作。已知超容量等已证明的问题仍保留。来源容器未报告初始物料时，不推断为已证实为空。

## 文件和审核

XDL 保留 `Synthesis / Metadata / Hardware / Reagents / Procedure`，扩展命名空间为 `urn:mosaic:xdl:extensions:1`。文件内嵌本次使用的合同、摘要、器材、试剂、上下文、步骤、原文和参数标识。封闭类型节点支持无损往返；未知 XML 节点、重复字段、DOCTYPE 和不一致合同被拒绝。原标准子集有独立严格校验；扩展文件不会标成标准平台编译通过。

审计网页显示扩展定义、来源参数标识和原文定位。审核动作是否表达准确、缺失标识是否符合原文；源参数缺失本身不再算提取失败。格式非法、虚构事实、动作遗漏等工具问题才进入未完成队列。

```powershell
# 默认启用自动扩展
python -m mosaic extract path/to/procedures --model operation_expander=gpt-6.1-sol
# 下一批复用操作库
python -m mosaic extract path/to/more --registry path/to/library_registry.json
# 显式使用原受限标准子集
python -m mosaic extract path/to/procedures --domain chemistry.batch/2
```
