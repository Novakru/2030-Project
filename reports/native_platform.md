# 原生平台参考流程

检查 101 份原生程序；类型解析通过 89；原图编译通过 64；未通过或缺图 37。

使用 Science 2022 配套源码中的 XDL 0.5.0、ChemputerXDL 1.0.0，源码原件保留且 SHA256 固定。Python 与运行时依赖版本在 native_platform.json，依赖由 requirements-platform.lock.txt 锁定。
适配处理单一 Synthesis 外层 XDL 包装、带明确体积/RPM 单位的属性别名，并为省略 pid 的 Async 提供稳定且不冲突的 ID；显式 ID 和 Await 关系保持原样。未知质量不换算为体积，柱色谱细节不补造。适配副本、原始哈希与更改列表分别保留。

编译开启内置 sanity checks，禁用交互。耗时估算所需控制器只允许 simulation=True，禁用网络、串口及真实控制器初始化；不执行实物实验。
作者成功分区和仅翻译分区分开保存。编译通过不改变 human_review、benchmark_eligible 或完整化学可行性状态。

通过记录：data/publications/platform_positives.jsonl；全部结果：data/publications/platform_validation.jsonl；编译文件：data/compiled/publication/。

| 未通过程序 | 分区 | 阶段 | 原因 |
|---|---|---|---|
| chemputer_2022_eee8e3046d0e1ee6 | successful_reactions | typed_parse | XDLError: PreparativeChromatography is not a valid step type. |
| chemputer_2022_4c440a90c757bdb1 | successful_reactions | typed_parse | XDLError: PreparativeChromatography is not a valid step type. |
| chemputer_2022_485622460c4312b6 | successful_reactions | typed_parse | XDLError: PreparativeChromatography is not a valid step type. |
| chemputer_2022_54e72e028d9f851a | successful_reactions | compile | ChempilerError: Trying to move to/from same node (buffer_flask). |
| chemputer_2022_8a0d79f7d4603d93 | successful_reactions | compile | ChempilerError: Trying to move to/from same node (buffer_flask). |
| chemputer_2022_7ca3a48a220ffde6 | successful_reactions | compile | ChempilerError: Trying to move to/from same node (flask_holding). |
| chemputer_2022_539a8adf80aeb408 | successful_reactions | typed_parse | XDLError: amount is not a valid attribute for Add. |
| chemputer_2022_2e52e84a0894fee8 | successful_reactions | typed_parse | XDLError: amount is not a valid attribute for Add. |
| chemputer_2022_d0a26627095a851a | successful_reactions | typed_parse | XDLError: amount is not a valid attribute for Add. |
| chemputer_2022_0a931b26e0558732 | successful_reactions | typed_parse | XDLError: amount is not a valid attribute for Add. |
| chemputer_2022_fc0847872cf5c53b | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_98aa7ee0d288b00e | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_3f57b043a65214d1 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_98090a5c02611a14 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_cbfc515daad7534d | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_ad3767a651c4fcfd | translated_XDLs | typed_parse | XDLError: amount is not a valid attribute for Add. |
| chemputer_2022_5385b678f6384149 | translated_XDLs | compile | XDLSanityCheckError: Trying to transfer through "Celite" but cannot find cartridge containing Celite.   Transfer   {'stir_to_vessel': False, 'stir_from_vessel': False, 'rinse_stir': True, 'stir_speed': 250.0, 'from_vesse |
| chemputer_2022_ffd6015d9433fa64 | translated_XDLs | compile | XDLSanityCheckError: Trying to transfer through "silica" but cannot find cartridge containing silica.   Transfer   {'stir_to_vessel': False, 'stir_from_vessel': False, 'rinse_stir': True, 'stir_speed': 250.0, 'from_vesse |
| chemputer_2022_c61a834d73ad6a49 | translated_XDLs | compile | XDLSanityCheckError: Trying to transfer through "silica" but cannot find cartridge containing silica.   Transfer   {'stir_to_vessel': False, 'stir_from_vessel': False, 'rinse_stir': True, 'stir_speed': 250.0, 'from_vesse |
| chemputer_2022_b750256a8fadb9a9 | translated_XDLs | typed_parse | XDLError: mass is not a valid attribute for Add. |
| chemputer_2022_909f72915fd057cb | translated_XDLs | compile | KeyError: 'reactor2' |
| chemputer_2022_3bd6c85341052adb | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_0a04bf1cabb4739b | translated_XDLs | compile | KeyError: 'waste_Z' |
| chemputer_2022_6dcb3278ae48d96e | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_9f03aa5abc41dfee | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_9a1ffc3aac03cdfd | translated_XDLs | typed_parse | XDLError: mass is not a valid attribute for Add. |
| chemputer_2022_bb314c3559bf1b82 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_6fc76d2c4f1f1c09 | translated_XDLs | compile | KeyError: 'filtrate_flask' |
| chemputer_2022_2a45bd691af328e9 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_9301c4514c2faff2 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_6fab666890a1dc02 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_20fa982340147dfc | translated_XDLs | compile | XDLSanityCheckError: Trying to transfer through "celite" but cannot find cartridge containing celite.   Transfer   {'stir_to_vessel': False, 'stir_from_vessel': False, 'rinse_stir': True, 'stir_speed': 250.0, 'from_vesse |
| chemputer_2022_eb8ae687a9742e00 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_c3df57dc29a3ff4e | translated_XDLs | compile | XDLSanityCheckError: Trying to transfer through "silica" but cannot find cartridge containing silica.   Transfer   {'stir_to_vessel': False, 'stir_from_vessel': False, 'rinse_stir': True, 'stir_speed': 250.0, 'from_vesse |
| chemputer_2022_2c19dfe6a5f6c646 | translated_XDLs | graph | MissingUniqueSourceGraph: 缺少唯一来源装置图 |
| chemputer_2022_51ea45864c2d3444 | translated_XDLs | typed_parse | XDLError: speed is not a valid attribute for Stir. |
| chemputer_2022_1e9fa1a3c8764592 | translated_XDLs | typed_parse | XDLError: speed is not a valid attribute for Stir. |
