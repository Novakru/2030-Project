# 5 条化学原文试验

`sources.json` 从此前工作区保存的 ORD 原始流程中选取 5 段完整 procedure，未裁剪或由结构化字段重建。输入仅包含 id、procedure 和出处；不包含 components、conditions、setup、temperature、duration 或产率字段。

| 来源 ID | 主要检查点 |
|---|---|
| ord-38cadda2a33648a9ad5bbd9f93ac95f2 | Schlenk flask、惰性气氛、两次柱纯化 |
| ord-dd820c31fef4456fb96fcbe0cfbfed80 | Schlenk tube、活化、脱气、弃置 |
| ord-000048416f294ed38b3a5181fc1060bf | 离心蒸发、移液、倒置、离心、热封板 |
| ord-0281c64afe8a4dee8619538b12e034d0 | 手套箱、多孔板装配、封闭、离心与取样 |
| ord-8a61495c860141f1a8046698b9543528 | microreactor 保留子型、压力盖、加热块 |

执行：`python -m mosaic extract examples/chemistry_pilot/sources.json --workers 2 --max-calls 90`。

这是表示质量的小规模试验，包含原文未给出的条件、未随附的图示设计及失败反应的叙述。不得根据器材惯例或其他记录填补这些内容；通过机器检查的记录仍为 silver，等待专家审计。JSON 与 XDL 产物留在忽略的 outputs 目录，复用库通过 `--registry` 指定。
