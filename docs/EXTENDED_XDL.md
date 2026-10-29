# XDL 导出与扩展

XML 保持 XDL 的元素／属性语法。聚类和规范化属于内部分析，不进入 XDL 文件。

```xml
<Synthesis>
  <Hardware><Component id="reactor" type="microreactor"/></Hardware>
  <Reagents><Reagent name="water" role="solvent"/></Reagents>
  <Parameters><Parameter id="p_mix_time__NOT_REPORTED__" type="time"/></Parameters>
  <Procedure>
    <Add reagent="water" vessel="reactor" volume="1 mL"/>
    <Stir vessel="reactor" time="p_mix_time__NOT_REPORTED__"/>
  </Procedure>
</Synthesis>
```

内部的 Mix(method=stir/shake/vortex) 分别导出为 Stir、Shake、Vortex；Heat 与同步搅拌可重新生成 HeatChill(stir=true)。操作族、composition 分组、operation_id、原始措辞和合同均保留在 `records.jsonl`。具体试剂名称直接写入 XML，不只输出内部试剂编号。

每条记录的 `xdl_extensions` 声明使用的非标准步骤／属性和器材类型；`xdl_bindings` 连接 XML 步骤位置与内部步骤。运行目录的 `xdl_extensions.json` 汇总这些旁文件信息。扩展声明不嵌入 XML，不包含执行代码。`libraries/xdl_steps.yaml` 维护标准步骤属性，表示合同仍由四份公共词汇文件维护。

缺失／定性／歧义参数生成带对应标识的未赋值 Parameter；其原始措辞留在 JSON 中。导出不会凭空填数、把微反应器认作连续流或修复错误设备引用。器材配置与额定值在来源 JSON 和器材库中维护。

验证器检查章节、声明的操作和属性、标识唯一性与引用，拒绝 DTD、外部实体和私有 XML 结构。重放对照冻结 JSON 重新生成 XML，核对文件和扩展声明；XML 不承担来源数据库的无损序列化职责。

结构依据：[XDL 文件结构](https://croningroup.gitlab.io/chemputer/xdl/standard/xdl_file_structure.html)、[标准步骤](https://croningroup.gitlab.io/chemputer/xdl/standard/full_steps_specification.html)、[参数](https://croningroup.gitlab.io/chemputer/xdl/standard/parameters.html)。结构检查不等于通过官方平台编译；新增操作仍需执行适配，物理可行性保留专家审核。
