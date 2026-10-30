# 五条新来源工程验证输入

sources.json 保存五条逐字原文，只包含 id、procedure、source。文本来自 ORD 的 Reaction.notes.procedure_details，未用投料、条件、器材或产物结构字段重建。许可 CC-BY-SA-4.0，逐条保留链接、反应和文本哈希。

排除了历史 220 条数据涉及的全部 11 个 dataset_id；五条来自其他 USPTO-grants 数据组。selection.json 记录获取和选择规则。原文没有用于编写样例特定分支或调节提取提示。

两个限制：数据查看接口的行版本未独立核验；DOI 可能指向共同 USPTO 发布集，不能证明五份原始专利彼此独立。这是数据组隔离的工程验证，不是有专家标签、严格论文隔离的准确率基准。真正盲测及后续灰度仍需专家参考。

```powershell
./.venv/Scripts/python.exe -m mosaic extract examples/chemistry_holdout/sources.json --workers 3 --max-calls 17 --max-seconds 900
```

明确指定 sources.json，README 和 selection.json 不是实验输入。运行前冻结源码、提示、库及评价规则；整批结束后一次分析，闸门失败则保留原因并讨论下一版本。
