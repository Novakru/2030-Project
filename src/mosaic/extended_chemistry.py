"""Default chemistry adapter: grow the representation vocabulary from source text."""
from __future__ import annotations

import copy

from protocol_risk.io import digest, load_library
from protocol_risk.validation import prepare_protocol, split_group

from .chemistry import ChemistryDomain
from .completion import complete


class ExtendedChemistryDomain(ChemistryDomain):
    name = "chemistry.extended/1"

    def _scope(self, raw):
        # A source operation need not have an instrument executor to be represented.
        # Execution availability is a separate, explicit property of its contract.
        return None

    def extract(self, raw, runner, *, use_model=True, critique=True, mapping=True):
        if not use_model:
            raise ValueError("Structured reconstruction is disabled; extraction requires procedure text")
        notes, protocol = {"domain": self.name}, None
        try:
            extracted = super().extract(raw, runner, use_model=True, critique=critique, mapping=mapping)
            protocol, notes = extracted["protocol"], extracted["notes"]
        except ValueError as error:
            # A failed core-only expression is useful diagnostic context, never
            # a reason to discard a physical action from the extended language.
            notes["core_expression_error"] = str(error)[:1000]
        result = complete(raw, protocol, self.registry(), runner)
        notes["completion"] = result["notes"]
        return {"protocol": result["protocol"], "notes": notes, "raw_id": raw["id"]}

    def validate(self, extracted, raw, run_id):
        protocol = copy.deepcopy(extracted["protocol"])
        protocol["id"] = "mosaic_pos_" + digest({"raw": raw["raw_sha256"], "protocol": protocol, "run": run_id})[:20]
        prepared = prepare_protocol(protocol, raw, extended=True)
        from .canonical import finalize_protocol
        snapshot = self.registry().snapshot
        prepared = finalize_protocol(prepared, vocabulary={
            "operations": snapshot.get("canonical_operations") or load_library("atomic_operations.yaml")["operations"],
            "mappings": snapshot.get("operation_mappings") or load_library("operation_mappings.yaml")})
        prepared["mosaic"] = {"schema": "mosaic.ir/2", "run_id": run_id, **extracted["notes"]}
        prepared["split_group"] = split_group(prepared)
        return prepared
