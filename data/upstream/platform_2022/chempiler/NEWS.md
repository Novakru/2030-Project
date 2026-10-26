# News

## Chempiler 0.6

### Breaking changes
---

* The Chempiler constructor signature has been simplified to:
```
Chempiler(exp_name, output_dir, graph, simulation)
```
`device_modules` can still be passed but defaults to `[ChemputerAPI]`

---
* The move signature has some changes:
	* The speed tuple has been replaced by `speed`, `initial_pump_speed` and `end_pump_speed`. `initial_pump_speed` is the speed with which to withdraw from src, and `end_pump_speed` is the speed with which to dispense into dest. If these are not given, they will take the value of `speed`. If none of these are given default values will be used.
	* `through_nodes` takes a node, or list of nodes through which the move path should go.
	* `use_backbone` if True will make the pathfinding choose a path that uses the backbone, if one exists. Using `through_nodes` makes `use_backbone` meaningless. 

```
chempiler.move(
	src,
	dest,
	volume,
	src_port="",
	dest_port="",
	speed=None,
	initial_pump_speed=None,
	end_pump_speed=None,
	through_nodes=[],
	use_backbone=True,
)
```

*  