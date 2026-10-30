# XDL 与配套数据

XML 使用普通 XDL 元素和属性。规范 ID、聚类、来源、事实树和合同不进入 XML。新操作可用专业步骤名和声明属性扩展；Stir、Shake、Vortex 保留混合方式差异。

同一投料的质量和物质的量同时写入 Add 的 mass、amount，不通过分子量补数。并列加料取一个合法线性次序，但 participant_order=unspecified 留在 Facts，不把次序当作唯一答案。明确同步的 Heat 和 Stir 合为 HeatChill(stir=true)，共享时长只执行一次。

缺参、定性和歧义使用未赋值 Parameter；定性原文另外保留。nominal_volume 等器材配置保存在按 Component ID 绑定的外部 hardware_config。microreactor 保持具体类型，不推断连续流、压力或几何信息。

每个 xdl/<id>.xdl 配有同名 .json，保存扩展声明、硬件配置、事件和事实位置、关系及观察。相同内容也在 records.jsonl 中供数据库导入。复制扩展 XDL 时应带上配套 JSON。

读取器独立检查章节、声明、标识和引用，拒绝 DTD、外部实体和私有类型树。保真检查读取实际属性，既检测遗漏，也检测无依据新增。未实现的并发降级保留事实并报错，复杂异步和循环尚未实现。

结构依据：[XDL 文件结构](https://croningroup.gitlab.io/chemputer/xdl/standard/xdl_file_structure.html)、[标准步骤](https://croningroup.gitlab.io/chemputer/xdl/standard/full_steps_specification.html)、[参数](https://croningroup.gitlab.io/chemputer/xdl/standard/parameters.html)。本地结构和事实检查不等于官方平台编译、实验可行性或设备执行认证。
