# 评价与参考答案

mosaic evaluate RUN_DIR 先验证冻结产物和真实 XML，再读取 --reference FILE。参考只用于评分，不发送给提取、核查或库维护模型。

参考包含 source_id、source_sha256（UTF-8 原文 SHA256）、entities、events、facts、relations。事实指定 required／optional／ambiguous、critical、值、归属、范围及证据。事件提供 operation_id 或 acceptable_operation_ids；器材提供 subtype_id 或 acceptable_subtype_ids。不能把局部草案直接改成完整参考。

专家确认后设置 is_gold=true、coverage_status=complete，并填写 manual_review={reviewer, reviewed_at, decision:accept, comment}。单独的 is_gold 标记不足以成为专家参考。接受一个转换记录，也不会自动为评分参考完成整套标注。

评分包括逐条 precision／recall／F1、数量打印值和单位、错误绑定及范围、事件和实体覆盖、关系覆盖、未知状态混淆及错误补数。使用严格一对一匹配，不用模糊文字相似度代替语义；专家认可的操作同义由稳定 ID 表达。属性遵循 Facts 语义槽位，不由模型在线裁决不同属性为相同事实。

部分参考只报告已标注范围内的 recall，precision、F1 和全局 FP 为空。没有参考则准确率为空。全部输入保留在端到端分母中；失败记录可按已有事实评分，但不能计成功 XDL。

批量闸门要求全部输入有完整专家参考、概念标注齐全、无关键误差或编译损失。微反应器文件是助手准备的未审核局部草案，不是 gold；新五条也没有人工参考。审计后再考虑同一冻结版本的 20–50 条灰度，不自动启动大规模任务。
