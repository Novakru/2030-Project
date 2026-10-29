# 历史需求

[jev_protocol_risk_spec.md](jev_protocol_risk_spec.md) 保留最初的 Jev 风险模型方案，内容未改写，供追溯需求使用。当前实现以根目录 README、MOSAIC 和规范词汇文档为准。

旧 `src/protocol_risk/jev.py` 是基于 ORD 结构化条件的 HTE 低产率逻辑回归训练脚本，不参与 MOSAIC 的纯文本提取、扰动或审计，也未获准充当风险判定器。它和无人调用的 `models/hte_baseline.joblib` 已从当前分支删除，历史版本可在 `d0ee1b7` 查阅。

当前冻结批次与验证报告来自提交 `d0ee1b7`，数据和人工审核状态未因本次代码清理更改。批次固定整个来源代码目录的哈希，删除无调用的脚本也会改变哈希，因此严格离线重放旧批次需要对应提交；不能绕过校验或改写旧批次的版本记录。
