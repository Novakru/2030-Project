# Evidence-grounded workflow state planning

Accessed 2026-10-30. Scope: architecture advice for literal protocol text to conventional, extensible XDL. No dependencies installed, extraction API called, runtime changed, or frozen `2b5ca0d` artifact altered. The graph contract is proposed in [PIPELINE_GRAPH_DESIGN.md](../PIPELINE_GRAPH_DESIGN.md).

## Recommendation

Use the proposed Pipeline layer to produce an evidence-grounded **material-state / operation graph**, not a freely rewritten sequence of prose instructions. Upgrade the existing extraction call to return this graph alongside facts; an independent checker compares both directly with the original text. Deterministic code validates and lowers the result to a chosen XDL profile. This is our engineering recommendation, not a capability supplied by any cited project.

The material-flow graph is directed and bipartite: `MaterialState -> Operation -> MaterialState`. Input edges carry explicit roles such as `added_material` and `receiver`; output edges distinguish `retained_solid` and `filtrate`. Separate temporal constraints and equipment relations avoid treating every relationship as a preceding action. Version state IDs and retain lineage; do not overwrite one global `mixture` object. Use bounded control blocks for explicitly reported loops rather than requiring every complete protocol to be a DAG.

For the reported sentence, retain:

```text
suspension_0 [A 25.4 g + B 11.3 g + ethanol 150 mL]
    -- receiver --> add_1 -- output --> mixture_1
methylate_solution_0 [15% sodium methylate in methanol]
    -- added_material (18 mL) --> add_1
```

`suspension_0` is a **reported initial state**; `add_1` is the reported action. The sentence does not report a preparation procedure for that suspension. A useful planning display may show “initial suspension required,” but must not assert “first prepare the suspension” as a source-reported step. The 18 mL belongs to the added portion; it is not the volume of the receiver. The percent concentration basis remains unreported unless supplied elsewhere in the text.

## Five primary reference groups and their actual support

1. **ACRA, Communications Chemistry (2026).** The published workflow separates procedure processing, XDL translation, parser feedback, original-procedure discrepancy checking, and hardware-constrained simulation. It explicitly says these checks do not guarantee completeness or accuracy. Its execution examples include approximated parameters and a changed extraction count; therefore its sanitization behavior is not an appropriate default for MOSAIC's literal-fidelity requirement. Borrow the separation of checks, not silent repair of source chemistry. The paper also reports modifications to its XDL parser and hardware mapping, so its result is not proof of compatibility with an arbitrary stock XDL installation. [Published paper, DOI 10.1038/s42004-026-01993-w](https://www.nature.com/articles/s42004-026-01993-w); [authors' repository](https://github.com/croningp/acra).

2. **Process Execution Graphs (PEG), EACL 2021.** The authors define a document-level representation for wet-lab biochemistry protocols addressing cross-sentence relations, coreference, grounding, and implicit arguments. Their annotation simulator tracks entity traits and semantic constraints. This supports choosing document-level state and relation modeling; it does not establish performance on synthetic chemistry or give MOSAIC a ready-made XDL compiler. [Paper and author abstract](https://arxiv.org/abs/2101.10244).

3. **Material State Transfer Graphs (MSTG), ACL 2021.** This work represents protocol flow through temporal/causal action relations across sentences and addresses implicit arguments and long-range dependencies. It supports explicitly modeling cross-step material flow instead of flattening local participants. The evaluated domain is wet-lab protocols; applicability to the present chemical corpus needs validation. [Publisher paper page](https://aclanthology.org/2021.acl-long.525/).

4. **LangExtract, first-party repository.** Extractions carry source-location grounding; outputs that cannot be located can have `char_interval=None`. Its examples favor verbatim extraction, and its own guidance distinguishes text evidence from world-knowledge inference. Adopt `source_id/start/end/quote` and verify spans in code. A located name or amount does not prove that its semantic role, scope, or coreference is correct. LangExtract is an optional reference implementation, not a required new runtime dependency. [Official repository and grounding guidance](https://github.com/google/langextract); [source data structures](https://github.com/google/langextract/blob/main/langextract/core/data.py).

5. **Official XDL 2.0 documentation.** The inspected documentation identifies itself as `2.0.1.dev12+g8fdf586b`. It defines `Hardware`, `Reagents`, and `Procedure` sections; procedure actions are linear by default. `Add` identifies the reagent and destination vessel; optional parameters include quantity, time, dropwise behavior, and stirring. Reagent declarations are not themselves instructions to charge a reactor. These support compiling typed roles into established step parameters. [File structure](https://croningroup.gitlab.io/chemputer/xdl/standard/xdl_file_structure.html); [step specification](https://croningroup.gitlab.io/chemputer/xdl/standard/full_steps_specification.html).

## XDL fidelity and executable lowering

The inspected standard sections do **not document a portable declaration of an arbitrary preloaded mixture with component quantities**, nor an epistemic “these additions occurred in an unknown order” group. This is a scoped documentation finding, not proof that no version or platform extension supports such facilities. Confirm the exact parser and adapter before claiming compatibility.

XDL 2.0 does document queues: steps in the same queue are sequential; different queues may execute in parallel subject to hardware locks. That is an execution scheduling mechanism. It does not establish that an unreported preparation order was parallel or that a selected order is chemically equivalent. Do not use queues merely to hide missing evidence. [Official scheduling semantics](https://croningroup.gitlab.io/chemputer/xdl/standard/scheduling_with_xdl.html).

Recommended profiles:

- **Fidelity:** preserve the initial-state precondition and unknown vessel in the graph/JSON. Export only supported XDL actions and a clear completeness/expressibility receipt. If the selected standard needs a vessel or initialization that is unavailable, report that executable output is unresolved; valid-looking XML is insufficient.
- **Initialization-enabled lowering:** derive required charges only under an explicit, versioned compiler policy. Mark them `compiler_derived_initialization`, retain `derived_from` fact IDs, and keep the unordered dependency group in the graph. If the target requires a linear order, use a separately approved platform policy or leave the dependency unresolved. Never claim the selected order was reported in the source.

Keep three origins distinct: `reported_action`, `reported_initial_state`, and `compiler_derived_initialization`. Structural outputs required by operation semantics, such as a possible filtrate node from filtration, also need explicit provenance; they do not imply that the source reported collection, composition, volume, or destination.

## Implementation constraints and forbidden inference

- Preserve existing stable fact IDs and source spans. Bind quantities to component, transferred portion, event, and scope; avoid a flat `participant_ids` list.
- Define operation roles and state effects in the versioned operation library. Extending that library is separate from extracting a protocol instance.
- Keep composition, graph edges, unresolved facts, and provenance in the JSON sidecar. Emit only parameters admitted by the target operation contract; do not create instance-shaped XML fields such as `subject_<id>_mass`.
- Require branch references to select residue versus filtrate explicitly. Do not silently send later residue processing to the filtrate.
- Do not infer preparation order, stirring, dissolution, temperature, duration, vessel subtype, phase composition after reaction, additive total volume, concentration basis, or a mechanism for vague “treated with” wording.
- Prefer one joint fact/graph extraction call, one independent source comparison, and at most one bounded local repair. These are proposed budget choices, not empirically established performance claims.
- Evaluate unsupported added actions, quantity ownership, input/receiver reversal, initial-state/action confusion, material lineage, branch selection, and graph-to-XML retention separately from JSON/XML validity. No citation demonstrates that MOSAIC already meets these criteria.
