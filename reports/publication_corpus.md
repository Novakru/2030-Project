# 作者原始 XDL 参考语料

来源：[Science 2022 作者数据包](https://zenodo.org/records/6534009)，DOI 10.5281/zenodo.6534009，CC BY 4.0。

- XML 与声明引用检查通过、去重后的程序：101。
- 作者分区：{'successful_reactions': 51, 'translated_XDLs': 50}。成功分区是作者报告，翻译分区不视为实测成功。
- 机械修复：2；待平台或人工确认：2。
- 文件校验与补丁复原审计：True。严格 gold：0。

原始 .xdl、装置图和作者编译文件在 data/upstream/chemputer_2022/；可检查的副本在 data/xdl/publication/。
修复仅涉及成对 XML 标签的大小写和能唯一匹配已声明名称的尾随空格，原始文件不变。每份副本有来源 SHA256、结果 SHA256、修复记录和 RFC 6902 差异。

这是独立参考语料，没有混入 ORD 正样本计数，也没有自动授予 benchmark_eligible 或 gold。静态检查不能证明全部化学步骤、预装物料、器材约束和实机执行均已确认。
部分作者程序从手工预装物料后的阶段开始；必须结合原文与装置记录检查流程范围。
通过 HTTP Range 只下载所需成员；ZIP CRC32 与成员 SHA256 已记录，未声称验证未完整下载的 ZIP 总校验和。
