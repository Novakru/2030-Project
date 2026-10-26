# 原子操作库统计

单一权威定义：libraries/primitives.yaml。

| 原子操作 | 本批已选流程出现次数 | 标准 XDL 映射 |
|---|---:|---|
| Add | 970 | Add |
| Transfer | 0 | Transfer |
| HeatChill | 140 | HeatChill, HeatChillToTemp |
| Stir | 19 | Stir |
| Wait | 0 | Wait |
| Atmosphere | 65 | Purge, EvacuateAndRefill |
| Separate | 0 | Separate |
| Filter | 0 | Filter, FilterThrough |
| Evaporate | 20 | Evaporate |
| Irradiate | 0 | Irradiate |
| Sonicate | 0 | 无确认映射，导出时隔离 |
| Purify | 19 | RunColumn |

覆盖率统计的分母仅为已接受 IR 中的操作。不能据此声称对全部原始文本文库已达到 ≥98% 的抽取覆盖率。
